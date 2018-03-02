from __future__ import absolute_import, division, print_function
from .version import __version__  # noqa
# from .gearificator import *  # noqa

__version__ = '0.0.1'

import logging


def get_logger(name=None):
    """Return a logger to use
    """
    return logging.getLogger('gearificator' + ('.%s' % name if name else ''))


_DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

lgr = get_logger()
# Basic settings for output, for now just basic
lgr.setLevel(logging.INFO)
FORMAT = '%(asctime)-15s [%(levelname)8s] %(message)s'
logging.basicConfig(format=FORMAT)

from nipype.interfaces.ants.registration import ANTS