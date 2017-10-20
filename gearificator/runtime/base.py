#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""

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

import os
import json
import sys

from glob import glob

from os.path import (
    join as opj,
    exists
)
from importlib import import_module

from gearificator.consts import (
    #MANIFEST_BACKEND_FIELD,
    MANIFEST_CUSTOM_SECTION,
    MANIFEST_CUSTOM_INTERFACE,
    MANIFEST_FILENAME,
    CONFIG_FILENAME,
)

from gearificator.exceptions import (
    UnknownBackend
)


from gearificator import get_logger
lgr = get_logger('runtime')
lgr.setLevel(10)  # DEBUG
# TODO: might want to beautify


def load_interface(module_cls):
    # import that interface and return the object
    module_name, cls_name = module_cls.split(':')  # TODO: robustify
    #topmod, submod = module_name.split('.', 1)
    module = import_module(module_name)
    return getattr(module, cls_name)


def load_interface_from_manifest(j):
    """Load the manifest.json and extract the interface definition
    """
    if not isinstance(j, (list, tuple)):
        # must be a filename
        j = load_json(j)
    try:
        module_cls = j['custom'][MANIFEST_CUSTOM_SECTION][MANIFEST_CUSTOM_INTERFACE]
    except Exception:
        raise ValueError("Did not find definition of the interface among %s"
                         % str(j.get('custom')))
    return load_interface(module_cls)


def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename) as f:
        return json.load(f)


def errorout(msg, exitcode=1):
    """Report Error and exit with non-0"""
    lgr.error(msg)
    sys.exit(exitcode)


def main():
    """The main "executioner" """

    topdir = os.environ.get('FLYWHEEL')  # set by Dockerfile
    indir = opj(topdir, 'input')
    outdir = opj(topdir, 'output')

    # Paranoia
    outputs = glob(opj(outdir, '*'))
    if outputs:
        errorout(
            "Yarik expected no outputs being present in output dir. Got: %s"
            % ', '.join(outputs)
        )

    # Load interface
    manifest = load_json(opj(topdir, MANIFEST_FILENAME))
    config = load_json(opj(topdir, CONFIG_FILENAME))

    interface_cls = load_interface_from_manifest(manifest)
    interface = interface_cls()

    # Parametrize it with configuration options
    # We do not need to pass defaults from manifest since there they are
    # the defaults as in nipype
    inputs = manifest.get('inputs')

    # tricky ones, yet to handle
    # probably analyze what inputs are present, and assign correspondingly
    for input_, input_params in inputs:
        input_dir = opj(indir, input_)
        filenames = None
        if exists(input_dir):
            filenames = glob(input_dir + '/*')
            if len(filenames) > 1:
                errorout("We do not speak multiple files yet per input")
                # TODO -- wild ideas. Provide an option to pair up
                # inputs.  E.g. if we have input/anatomy/sub{1,2,3}.nii,
                # input/mask/common.nii, input/func/sub{1,2,3}.nii
                # we could then loop nicely, and produce multiple outputs in the
                # same run.  Is it practiced in any gear?
            elif len(filenames) == 1:
                filename = filenames[0]
                setattr(interface.inputs, input_, filename)
        if not filenames:
            lgr.warning("No input for %s was provided", input_)

    # Further configuration
    for c, v in config.items():
        if c not in inputs:
            lgr.warning(
                "%s is not known to inputs, which know only about %s",
                c, inputs.keys()
            )
        setattr(interface.inputs, c, v)

    # Now we need to get through the outputs!
    # flywheel does not yet provide options to specify outputs, so we
    # will stick them into custom:gearificator-outputs
    interface.inputs.out_file = opj(outdir, "TODO")

    try:
        out = interface.run()
    except Exception as exc:
        lgr.error("Error while running %s", interface_cls)
    finally:
        # Should we clean up anything??  may be some workdir
        pass

    # Handle outputs

    # Check if anything under outdir
    # TODO: ATM only flat
    outputs = glob(opj(outdir, '*'))
    if not outputs:
        errorout("Yarik expected some outputs, got nothing")

    # But there is may be nothing really todo in our case?
    # May be some other interfaces would want to do something custom, we will
    # just save results