#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:
"""Interfaces and workflows of Nipype

 COPYRIGHT: Yaroslav Halchenko 2017

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

from __future__ import absolute_import

import nipype
import re
from collections import OrderedDict
from nipype.interfaces.base import traits

from . import nipype_handlers

# TODO: Should become part of some kind of a recipe
#       which would prescribe the environment and then what
#       interface is being gearified, with possible tune ups and options
DOCKER_BASE_IMAGE = "neurodebian:stretch"
#DOCKER_IMAGE = "gearificator:ants-test"  # neurodebian:stretch"
DEB_PACKAGES = [
   # 'ants',  # possibly versioned   ants=2.2.0-1
    'python-nipype',  # probably actually would need pip install it
]
PIP_PACKAGES = [
    # most likely we will need master of nipype for a while
    # if we are to contribute/extend docs etc
    # 'git+https://github.com/nipy/nipype'
]
LICENSE = ['BSD-3-Clause']
# not needed here but in general, should be a part of the specific
# recipe, depends on the app/pkg/etc
# SOURCE_FILE =
# ADD_PATH =

import logging
lgr = logging.getLogger('gearificator.nipype')


def get_version():
    import nipype
    return ".nipype.%s" % nipype.__version__


def analyze_spec(spec_cls, order_first=None, defaults={}):
    """Given the Spec class, extract the instances and interesting fields"""
    spec = spec_cls()
    config = OrderedDict()
    inputs = OrderedDict()
    for opt, trait in spec.items():
        # We better skip some, at least for now,
        # TODO: some might be specific to interfaces or too generic for which
        # we do not care to expose in the gear ATM
        if opt in {
            'ignore_exception',
            'terminal_output',
            'environ',
        }:
            continue
        if opt.endswith('_trait'):
            # those which are used later within actual config
            # options definitions
            continue
        try:
            handler, handler_name = get_trait_handler(trait)
        except ValueError as exc:
            lgr.warning("No handler for %s: %s", opt, exc)
            continue
        if not handler:
            continue

        trait_rec = handler(trait, default=defaults.get(opt))
        if trait_rec:
            desc = trait_rec.get('description')
            if not desc or desc.startswith(' [default'):
                # quite often options are "self-descriptive" so we will take the name
                # and use it as a description with minor changes
                new_desc = opt.capitalize().replace('_', ' ')
                # TODO: move into a function.  Add tune ups like  Num (of)? -> Number of
                if desc:
                    # add back the default
                    new_desc += desc
                trait_rec['description'] = new_desc
            # for now if 'xor', make it optional
            if trait_rec.pop('xor', None):
                trait_rec['optional'] = True
                # TODO: later we might want to explicitly store them in custom to
                # deal with them somehow more wisely
            if 'optional' in trait_rec and 'default' in trait_rec:
                # if default is set - there should be no optional
                trait_rec.pop('optional')
        if trait_rec is None:
            lgr.warning('Handler returned None for %s of trait %s', opt, trait)
        else:
            # Directory could be an output directory name specification  TODO figure out what to eat it with?
            if handler_name in {
                'File',
                'InputMultiPath', 'OutputMultiPath', 'InputMultiObject', 'OutputMultiObject'
                }:  # , 'Directory'}:
                inputs[opt] = trait_rec
            else:
                # we need to massage it a bit since apparently web ui does not
                # understand "optional" for configs
                # It will!
                # optional = trait_rec.pop('optional', False)
                # if optional:
                #     if 'default' not in trait_rec:
                #         trait_rec['default'] = None
                config[opt] = trait_rec
    config = get_entries_ordered(config)
    inputs = get_entries_ordered(inputs, order_first)
    return config, inputs


def get_entries_ordered(od, order_first=None):
    """Get OrderedDict sorted so non-optional come first

    Parameters
    ----------
    order_first: str
      Prefix to place first as well (within optional or not group)

    """
    if order_first is not None:
        key = lambda x: (bool(x[1].get('optional')), x[0].startswith(order_first), x[0])
    else:
        key = lambda x: (bool(x[1].get('optional')), x[0])
    return od.__class__(
        sorted(
            od.items(),
            key=key
        )
    )


def get_trait_handler(trait):
    """Given a trait, return a handler and its name
    """
    trait_type_class = trait.trait_type.__class__
    trait_type = trait_type_class.__name__
    # strip/change prefixes
    handler_name = trait_type.replace('traits.trait_types.', '')
    handler_name = handler_name.replace('nipype.interfaces.base.', 'nipype_')
    handler = getattr(nipype_handlers, handler_name, None)
    if not handler:
        import pdb; pdb.set_trace()
        raise ValueError("No handler for %s" % handler_name)
    return handler, handler_name


def extract_manifest(cls, defaults={}):
    """

    Parameters
    ----------
    cls
      Class to extract the manifest from/for

    Returns
    -------

    """
    # will be a mix of options and "inputs" (identified by using Files)
    config, inputs = analyze_spec(cls.input_spec, defaults=defaults, order_first='in')
    #  Not yet sure if actually needed right here since outputs are not
    #  part of the manifest
    config_out, outputs = analyze_spec(cls.output_spec, defaults=defaults, order_first='out')
    if config_out:
        assert False, "expecting only files in the output, not config settings. Got %s" % config_out
    # strip outputs of unneeded fields
    # may be eventually we would bring some back
    for v in outputs.values():
        for f in 'base', 'optional':
            v.pop(f, None)
    # TODO: in some cases outputs might have the same field as
    # declared in inputs (e.g. 'out_file' in BET). How do we deal with it?
    # One way is at the run time, in case user specified that one,
    # we use it somehow
    manifest = OrderedDict()

    # None values are placeholders so we could mandate a sane order of those
    # fields
    manifest['name'] = ('%s.%s' % (cls.__module__, cls.__name__)).lower().replace('.', '-')
    manifest['label'] = None
    # TODO: fill out what we could about stuff
    # TODO: 'custom':'docker-image'
    #manifest['author'] = 'Some authors, possibly from a recipe/API'
    #manifest['description'] = 'Some description, e.g. %s' % cls.__doc__
    cls_doc = getattr(cls, '__doc__')
    if cls_doc:
        # take the first line as a description
        manifest['description'] = cls_doc.split('\n')[0]
    manifest['author'] = None
    manifest['maintainer'] = None
    manifest['license'] = None
    manifest['version'] = None

    manifest['config'] = config or {}
    manifest['inputs'] = inputs or {}

    manifest['url'] = "http://nipype.readthedocs.io/en/%s/interfaces/generated/interfaces.ants/registration.html" % nipype.__version__
    # TODO:  license -- we should add the license for the piece?

    return manifest, outputs


def get_suite(obj, docker_image=None):
    """Given the object deduce the "suite" for the Flywheel spec for groupping
    """
    names = obj.__module__.split('.')
    assert names[0] == 'nipype'
    assert names[1] == 'interfaces'

    suite = "Nipype %s" % names[2].upper()
    if docker_image:
        # TODO: add a check if docker image exists already
        # and if not -- add "unknown" as the version
        from ..gear import subprocess_call
        dpkg_output, err = subprocess_call(
            ['docker', 'run', '--rm', '--entrypoint=dpkg', docker_image, '-l',
             {'fsl': 'fsl-core'}.get(names[2].lower(), names[2].lower())
             ]
        )

        suite += " %s" \
            % get_pkg_version(dpkg_output).split(':', 1)[-1].split('.')[0]
    return suite


def get_pkg_version(dpkg_output):
    hits = [l for l in dpkg_output.splitlines() if l.startswith('ii ')]
    assert len(hits) == 1
    return hits[0].split()[2]


def test_get_pkg_version():
    assert get_pkg_version("""Desired=U
||/ Name           Version        Architecture Description
+++-==============-==============-============-=========================================
ii  fsl-core       5.0.9-4~nd90+1 all          metapackage for the latest version of FSL
    """) == "5.0.9-4~nd90+1"
    assert get_pkg_version("ii  fsl-core       1:6.0.9-4") == "1:6.0.9-4"


def test_get_suite():
    # temp one
    from nipype.interfaces.fsl.preprocess import ApplyWarp
    assert get_suite(ApplyWarp, 'gearificator/nipype-interfaces-fsl-preprocess-fast:0.0.2.nipype.1.0.3.1')
