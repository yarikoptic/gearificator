"""Interfaces and workflows of Nipype"""
# for some reason was not sufficient here! so just renamed to _nipype
from __future__ import absolute_import
from collections import OrderedDict
from nipype.interfaces.base import traits

from . import nipype_handlers

# TODO: Should become part of some kind of a recipe
#       which would prescribe the environment and then what
#       interface is being gearified, with possible tune ups and options
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
    configs = OrderedDict()
    files = OrderedDict()
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
            lgr.warning("No handler for %s of %s (%s)", opt, trait_type_class, trait_handler)
            continue
        trait_rec = handler(trait)
        if trait_rec is None:
            lgr.warning("Handler returned None for %s", trait)
        else:
            (files if trait_handler in {'File', 'InputMultiPath'} else configs)[opt] = trait_rec
    return configs, files


def extract_manifest(cls, **fields):
    """

    Parameters
    ----------
    cls
      Class to extract the manifest from/for
    fields
      Additional fields to place into the manifest

    Returns
    -------

    """
    # will be a mix of options and "inputs" (identified by using Files)
    config, inputs = analyze_spec(cls.input_spec)
    #  Not yet sure if actually needed right here since outputs are not
    #  part of the manifest
    # output_spec = analyze_spec(cls.output_spec)

    manifest = OrderedDict()
    manifest.update(sorted(fields.items()))

    manifest['name'] = cls.__name__
    # TODO: fill out what we could about stuff
    # TODO: 'custom':'docker-image'

    if config:
        manifest['config'] = config
    if inputs:
        manifest['inputs'] = inputs

    #manifest['author'] = 'Some authors, possibly from a recipe/API'
    #manifest['description'] = 'Some description, e.g. %s' % cls.__doc__
    return manifest


def prepare_dockerfile():
    raise NotImplementedError


def prepare_run():
    """Prepare run script

    Should call into gearificator runner, which would invoke
    the actual computation so be quite minimalistic,
    should use manifest, and output specs
    (stored somewhere) to accomplish the mission
    """

    #
    raise NotImplementedError


# TODO: mark it as the entry point, or may be eventually should be
# called by the entry point depending on which interface was wrapped
def runner():
    """Actual runner of the computation, invoked within gear

    Returns
    -------

    """
    """
if [[ -f $CONFIG_FILE ]]; then
  eval $(jq -r '.config | to_entries[] | "config_\(.key)=\(.value)"' 
  $CONFIG_FILE)
else
  CONFIG_FILE=$FLYWHEEL_BASE/manifest.json
  eval $(jq -r '.config | to_entries[] | "config_\(.key)=\(.value.default)"' 
  $CONFIG_FILE)
fi

    """