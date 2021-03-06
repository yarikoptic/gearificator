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
import re
import shutil

from .cli_base import cli
from .consts import \
    GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_MANIFEST_FILENAME
from .utils import (
    md5sum,
    PathRoot
)

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
        if '/' not in in_file:
            raise ValueError("input file (got %r) is missing a path" % in_file)
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
        # Relative to d path
        dname = op.relpath(path, d)
        r.extend([op.join(dname, f) for f in fnames])
    return set(r)


def check_nib_diff(target, output):
    from nibabel.cmdline.diff import diff
    nib_diff = diff([target, output])
    if nib_diff:
        diffs = [
            "%10s: %s != %s" % (k, str(v1), str(v2))
            for k, (v1, v2) in nib_diff.items()
        ]
        diffs = (os.linesep + "  ").join([''] + diffs)
        return "nibabel diff (target, output):%s" % diffs


def check_md5(target, output):
    target_md5 = md5sum(target)
    output_md5 = md5sum(output)
    if target_md5 != output_md5:
        return "md5 mismatch (target, output): %s != %s" \
               % (target_md5, output_md5)


from collections import defaultdict


class TestDrivers(object):
    """A helper to provide test "drivers" for a given file """
    DRIVERS = {
        '.*\.nii\.gz': check_nib_diff,
    }
    # heh, starts to bind to the instance etc... didn't know
    #DEFAULT = check_md5

    def __call__(self, filename):
        matched_any = False
        for file_regex, driver in self.DRIVERS.items():
            if re.match(file_regex, filename):
                matched_any = True
                yield driver
        if not matched_any:
            yield check_md5

test_drivers = TestDrivers()


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
    only_in_output = output_files - target_files
    if only_in_output:
        raise AssertionError("Unexpected files in output: %s" % only_in_output)
    only_in_target = target_files - output_files
    if only_in_target:
        raise AssertionError("Expected files were not found in output: %s"
                             % only_in_target)
    failures = {}
    for f in target_files:
        # verify the content match
        target_file = op.join(target, f)
        output_file = op.join(outputdir, 'output', f)
        for test_driver in test_drivers(target_file):
            test_failure = test_driver(target_file, output_file)
            if test_failure:
                lgr.error("Failure %s: %s", f, test_failure)
                failures[f] = test_failure

    if failures:
        raise AssertionError("%d out of %d file(s) differ" % (len(failures), len(target_files)))


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
