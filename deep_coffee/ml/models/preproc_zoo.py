import sys

import tensorflow as tf

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


PREPROC_FN_ZOO = {
    "mobilenet": tf.keras.applications.mobilenet.preprocess_input,
    "vgg16": tf.keras.applications.vgg16.preprocess_input, # https://github.com/tensorflow/tensorflow/issues/29931
    "resnet50": tf.keras.applications.mobilenet.preprocess_input, # https://github.com/tensorflow/tensorflow/issues/29931
    "densenet": tf.keras.applications.densenet.preprocess_input,
    "inception_v3": tf.keras.applications.inception_v3.preprocess_input,
    "coffee_net_v1": tf.keras.applications.mobilenet.preprocess_input,
}


def get_preproc_fn(model_name):
    """ Get a Tensorflow model """
    if model_name not in PREPROC_FN_ZOO:
        logger.error('preproc_fn {} does not exist')
        sys.exit(1)

    logger.info('Loading preproc_fn {}'.format(model_name))
    preproc_fn = PREPROC_FN_ZOO[model_name]
    return preproc_fn
