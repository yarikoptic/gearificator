#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""Handle spec tests

"""

__author__ = 'yoh'
__license__ = 'MIT'

import click
import yaml
import json
import os
import os.path as op
import shutil

from .cli_base import cli
from .consts import \
    GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_MANIFEST_FILENAME
from .utils import PathRoot

from . import get_logger
lgr = get_logger('spec_tests')

# This one doesn't allow to look for a specific dataset... TODO
find_datasets_path = PathRoot(lambda s: op.exists(op.join(s, 'inputs')))


def _prepare(testfile, outputdir):
    with open(testfile) as f:
        test_spec = yaml.load(f)
    lgr.debug("Loaded test spec: %s", test_spec)
    # TODO: validate test schema
    # we will allow to override for now
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)
    gear_indir = op.join(outputdir, GEAR_INPUTS_DIR)
    gear_outdir = op.join(outputdir, GEAR_OUTPUT_DIR)
    for d in gear_indir, gear_outdir:
        if not os.path.exists(str(d)):
            os.makedirs(str(d))

    # Copy inputs
    lgr.debug(" copying inputs")
    datasets_path = find_datasets_path(testfile)
    if not datasets_path:
        raise RuntimeError("Did not find 'inputs/' directory with datasets")
    datasets_path = op.join(datasets_path, 'inputs')
    lgr.debug(" considering datasets under %s", datasets_path)
    for in_name, in_file in test_spec.get('inputs').items():
        in_dataset, in_dataset_path = in_file.split('/', 1)
        in_path = op.join(datasets_path, in_file)
        # copy under inputs/in_name/basename(in_file)
        dst_dir = op.join(gear_indir, in_name)
        dst_path = op.join(dst_dir, op.basename(in_dataset_path))
        if not op.exists(dst_dir):
            os.makedirs(dst_dir)
        lgr.debug(" copying %s to %s", in_path, dst_path)
        shutil.copyfile(in_path, dst_path)

    # Generate config
    lgr.debug(" generating config.json")
    with open(op.join(outputdir, 'config.json'), 'w') as f:
        # needs to be nested within 'config' item AFAIK
        # needs inputs as well TODO
        json.dump(
            {
                'config':  test_spec.get('config', {})
            },
            f,
            indent=2
        )

    # Copy manifest.json for the gear should happen outside


def get_files(d):
    r = []
    for path, dnames, fnames in os.walk(d):
        #r.extend([os.path.join(path, x) for x in fnames])
        # we need relative paths but probably later would need to sill handle
        # subdirs etc
        r.extend(fnames) # [os.path.join(path, x) for x in fnames])
    return set(r)


def _check(testfile, outputdir):
    """Given a testfile spec and output directory, perform all the tests

    ATM would just compare produced outputs to the target ones 1-to-1
    """
    # TODO: ATM just a basic comparator of files (without even subdirs etc)
    assert testfile.endswith('.yaml')
    target, _ = op.splitext(testfile)
    # target = op.join(target, 'output') # ??? do we need output there???
    # TODO: later all tests might be just based on "fingerprints" so no
    # target files might be needed
    target_files = get_files(target) if os.path.exists(target) else set()
    output_files = get_files(op.join(outputdir, GEAR_OUTPUT_DIR))
    #import pdb; pdb.set_trace()
    only_in_output = output_files - target_files
    if only_in_output:
        raise AssertionError("Unexpected files in output: %s" % only_in_output)
    only_in_target = target_files - output_files
    if only_in_target:
        raise AssertionError("Expected files were not found in output: %s"
                             % only_in_target)
    for f in target_files:
        # verify the content match
        pass


# CLI

@cli.group('test')
def grp():
    """Commands to assist with the tests"""
    pass

@grp.command(short_help="Prepare a test case")
@click.argument('testfile', type=click.Path(exists=True))  #, doc='File with test specification')
@click.argument('outputdir')  #, doc='Output directory.  Will be created if does not exist')
def prepare(*args, **kwargs):
    """Prepare a test case: inputs, config.json, etc"""
    return _prepare(*args, **kwargs)


@grp.command(short_help="Check the results for a ran test")
@click.argument('testfile', type=click.Path(exists=True))  #, doc='File with test specification')
@click.argument('outputdir', type=click.Path(exists=True))  #, doc='Output directory.  Will be created if does not exist')
def check(*args, **kwargs):
    return _check(*args, **kwargs)
