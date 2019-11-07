
import logging
from deep_coffee.ml.models import model_zoo
from deep_coffee.ml.utils import list_tfrecords, PlotConfusionMatrixCallback
from tensorflow_transform import TFTransformOutput
from tensorflow_transform.beam.tft_beam_io import transform_fn_io
import tensorflow as tf
import argparse
import yaml
import os
import datetime

import multiprocessing
N_CORES = multiprocessing.cpu_count()

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def input_fn(tfrecords_path,
             tft_metadata,
             image_shape,
             batch_size=8,
             shuffle=True,
             repeat=True):
    """ Train input function
        Create and parse dataset from tfrecords shards with TFT schema
    """

    def _parse_example(proto):
        return tf.io.parse_single_example(proto, features=tft_metadata.transformed_feature_spec())

    def _split_XY(example):
        X = {}
        Y = {}

        image_tensor = tf.io.decode_jpeg(
            example['image_preprocessed'], channels=3)
        image_tensor = tf.reshape(image_tensor, image_shape)
        X['input_1'] = image_tensor / 255
        Y['target'] = example['target']

        return X, Y

    num_parallel_calls = N_CORES-1
    if num_parallel_calls <= 0:
        num_parallel_calls = 1

    dataset = tf.data.TFRecordDataset(tfrecords_path, compression_type="")
    dataset = dataset.map(_parse_example,
                          num_parallel_calls=num_parallel_calls)
    dataset = dataset.map(_split_XY, num_parallel_calls=num_parallel_calls)
    dataset = dataset.prefetch(tf.data.experimental.AUTOTUNE)
    dataset = dataset.batch(batch_size)
    
    if shuffle:
        dataset = dataset.shuffle(buffer_size=batch_size * 5)
    
    if repeat:
        dataset = dataset.repeat()

    return dataset


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--tft_artifacts_dir', required=True)
    parser.add_argument('--input_dim', required=False, default=224, type=int)
    parser.add_argument('--trainset_len', required=True, type=int)
    parser.add_argument('--evalset_len', required=True, type=int)
    parser.add_argument('--testset_len', required=True, type=int)
    parser.add_argument('--config_file', required=True)
    parser.add_argument('--transfer_learning',
                        required=False, action='store_true')
    args = parser.parse_args()

    input_shape = [args.input_dim, args.input_dim, 3]

    config = yaml.load(tf.io.gfile.GFile(args.config_file).read())

    logger.info('Load tfrecords...')
    tfrecords_train = list_tfrecords(config['tfrecord_train'])
    logger.info(tfrecords_train[:3])
    tfrecords_eval = list_tfrecords(config['tfrecord_eval'])
    logger.info(tfrecords_eval[:3])
    tfrecords_test = list_tfrecords(config['tfrecord_test'])
    logger.info(tfrecords_test[:3])

    # Load TFT metadata
    tft_metadata_dir = os.path.join(
        args.tft_artifacts_dir, transform_fn_io.TRANSFORM_FN_DIR)
    tft_metadata = TFTransformOutput(args.tft_artifacts_dir)

    model = model_zoo.get_model(
        config['network_name'], input_shape=input_shape, transfer_learning=config['transfer_learning'])
    logger.info(model.summary())

    model.compile(optimizer=tf.keras.optimizers.Adam(lr=config['learning_rate']),
                  loss='sparse_categorical_crossentropy',
                  metrics=['accuracy'])

    steps_per_epoch_train = args.trainset_len // config['batch_size']
    steps_per_epoch_eval = args.evalset_len // config['batch_size']
    steps_per_epoch_test = args.testset_len // config['batch_size']

    datetime_now_str = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    output_dir = os.path.join(args.output_dir, datetime_now_str)
    ckpt_dir = os.path.join(output_dir, 'model.ckpt')
    tensorboard_dir = os.path.join(output_dir, 'tensorboard')

    callback_save_ckpt = tf.keras.callbacks.ModelCheckpoint(filepath=ckpt_dir,
                                                            monitor='val_loss',
                                                            save_best_only=True,
                                                            save_freq='epoch')
    callback_tensorboard = tf.keras.callbacks.TensorBoard(log_dir=tensorboard_dir,
                                                          histogram_freq=2,
                                                          write_graph=True,
                                                          write_images=False,
                                                          update_freq='epoch')
    callback_early_stop = tf.keras.callbacks.EarlyStopping(monitor='val_loss',
                                                           min_delta=5e-5,
                                                           patience=20)

    callback_plot_cm = PlotConfusionMatrixCallback(eval_input_fn=input_fn(tfrecords_eval,
                                                                          tft_metadata,
                                                                          input_shape,
                                                                          config['batch_size'],
                                                                          shuffle=False,
                                                                          repeat=False),
                                                   class_names=[
                                                       'Bad Beans', 'Good Beans'],
                                                   logdir=tensorboard_dir)

    model.fit(x=input_fn(tfrecords_train,
                         tft_metadata,
                         input_shape,
                         config['batch_size']),
              validation_data=input_fn(tfrecords_eval,
                                       tft_metadata,
                                       input_shape,
                                       config['batch_size'],
                                       shuffle=False),
              steps_per_epoch=steps_per_epoch_train,
              validation_steps=steps_per_epoch_eval,
              epochs=config['epochs'],
              callbacks=[callback_save_ckpt,
                         callback_tensorboard,
                         callback_plot_cm])

    # train_spec = tf.estimator.TrainSpec(
    #     input_fn=lambda: input_fn(tfrecords_train,
    #                               tft_metadata,
    #                               input_shape,
    #                               config['batch_size']))
    # # max_steps=steps_per_epoch_train*args.epochs)

    # eval_spec = tf.estimator.EvalSpec(
    #     input_fn=lambda: input_fn(tfrecords_eval,
    #                               tft_metadata,
    #                               input_shape,
    #                               config['batch_size']))
    # # steps=steps_per_epoch_eval*args.epochs)

    # run_config = tf.estimator.RunConfig(
    #     model_dir=args.output_dir,
    #     save_summary_steps=1000,
    #     save_checkpoints_steps=1000,
    #     keep_checkpoint_max=1
    # )

    # model_estimator = tf.keras.estimator.model_to_estimator(
    #     keras_model=model, config=run_config)

    # logger.info('Train')
    # tf.estimator.train_and_evaluate(estimator=model_estimator,
    #                                 train_spec=train_spec,
    #                                 eval_spec=eval_spec)