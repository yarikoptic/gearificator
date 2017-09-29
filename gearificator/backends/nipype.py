"""Interfaces and workflows of Nipype"""
# for some reason was not sufficient here! so just renamed to _nipype
from __future__ import absolute_import
from collections import OrderedDict
from nipype.interfaces.base import traits

from . import nipype_handlers

# TODO: Should become part of the recipe
DOCKER_BASE_IMAGE = "neurodebian:stretch"
DEB_PACKAGES = [
    'ants',  # possibly versioned   ants=2.2.0-1
]
PIP_PACKAGES = [
    # most likely we will need master of nipype for a while
    # if we are to contribute/extend docs etc
    'git+https://github.com/nipy/nipype'
]
# not needed here but in general, should be a part of the specific
# recipe, depends on the app/pkg/etc
# SOURCE_FILE =
# ADD_PATH =

import logging
lgr = logging.getLogger('gearificator.nipype')


def analyze_spec(spec_cls):
    """Given the Spec class, extract the instances and interesting fields"""
    spec = spec_cls()
    items = OrderedDict()
    for opt, trait in spec.items():
        # We better skip some, at least for now,
        # TODO: some might be specific to interfaces
        if opt in {
            'ignore_exception',
            'terminal_output',
        }:
            continue
        trait_type_class = trait.trait_type.__class__
        trait_type = trait_type_class.__name__
        # strip/change prefixes
        trait_handler = trait_type.replace('traits.trait_types.', '')
        trait_handler = trait_handler.replace('nipype.interfaces.base.', 'nipype_')
        handler = getattr(nipype_handlers, trait_handler, None)
        if handler is None:
            lgr.warning("No handler for %s (%s)", trait_type_class, trait_handler)
            continue
        trait_rec = handler(trait)
        if trait_rec is None:
            lgr.warning("Handler returned None for %s", trait)
        else:
            items[opt] = trait_rec
    return items


def extract(cls):
    # will be a mix of options and "inputs" (identified by using Files)
    input_spec = analyze_spec(cls.input_spec)
    output_spec = analyze_spec(cls.output_spec)

    # TODO: separate inputs from config
    config = input_spec

    manifest = OrderedDict()
    manifest['name'] = cls.__name__
    # TODO: fill out what we could about stuff
    # TODO: 'custom':'docker-image'

    manifest['config'] = config
    # TODO: what to do with that one??
    # ??? = output_spec
    return manifest

