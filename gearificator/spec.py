"""Handle the spec prescribing how to traverse and create gear(s)
"""

import click
import re
import sys
import os.path as op
import os
import shutil
import subprocess
import tempfile

from glob import glob
from os.path import join as opj
from inspect import ismodule
from itertools import chain
from . import get_logger
from .main import create_gear
from .utils import import_module_from_file
from .consts import  GEAR_MANIFEST_FILENAME, GEAR_RUN_FILENAME

lgr = get_logger('spec')

from .spec_tests import _prepare, _check


def load_spec(path):
    mod_spec = import_module_from_file(op.join(path, 'spec.py'))
    spec = mod_spec.spec
    assert '%path' not in spec
    spec['%path'] = path
    return spec


def get_updated(old, new):
    """Return updated structure/value

    If new value is a scalar, it overrides the previous value.
    If it is a list, and old one is a list - returned value is a concatenation.
    If it is a dict,
    In either of the above cases if old value is None, new one is provided
    """
    if not old:
        return new
    if isinstance(new, list):
        assert isinstance(old, list)
        return old + new
    elif isinstance(new, dict):
        assert isinstance(old, dict)
        # we need to "meld" them while also updating values
        out = old.__class__()
        # we will try to preserve the order just in case original was
        # ordered dict or alike
        for k in chain(old, new):
            if k in out:
                continue  # we already saw it
            if k in old:
                old_ = old[k]
                if k in new:
                    v = get_updated(old_, new[k])
                else:
                    v = old_
            else:
                v = new[k]
            out[k] = v
        return out
    else:
        lgr.debug(
            "Forgetting old value %r since new one %r is neither dict or list",
            old, new
        )
        return new


def get_object_from_path(path, attr=None):
    """Get the object given a path

    If some analysis was done already and path was split into possible
    lead path and remaining attr, that was is provided in attr
    """
    if not path:
        raise ValueError(
            "Cannot figure out anything from an empty path. Remaining attr=%s"
            % attr)

    if path in sys.modules:
        # shortcut
        mod = sys.modules[path]
    else:
        # else we should try to import as is
        path_split = path.rsplit('.', 1)
        topmod = None if len(path_split) == 1 else path_split[0]
        try:
            mod = __import__(path, fromlist=[topmod])
        except ImportError:
            # Might have been not a module
            attr_full = path_split[-1] if not attr else '.'.join([path_split[-1], attr])
            return get_object_from_path(topmod, attr_full)

    assert mod
    # so we imported something
    if not attr:  # just a shortcut
        return mod

    # if there is attr we should get to it
    ret = mod  # start from the module
    for a in attr.split('.'):
        ret = getattr(ret, a)
    return ret


class SkipProcessing(Exception):
    pass


def get_gear_dir(path):
    """Custom tune up for the gear path to eliminate subpaths which are of no
    interest and convert into directories
    """
    # TODO: figure out a better/more reliable way
    comps = filter(lambda p: p not in {"interfaces", "preprocess", "registration"},
                   path.split('.'))
    return op.join(comps)


def _process(
        outputdir,  # if none provided -- nothing would be saved
        spec=None,  # TODO: make configurable
        regex=None,
        run_tests=False,
        gear=None,
        toppath=None,
        actions=None,
        params={
            'recurse': False
        }
):
    """

    Parameters
    ----------
    spec: dict
    outputdir: str
    regex: str, optional
      Regular expression as to which paths to process
    actions: list of str
      What actions to perform, known ones: ...
    include: dict, optional
    manifest: dict, optional
    params: dict, optional

    Returns
    -------
    None
    """

    lgr.log(5, toppath)
    # first process all % entries
    params_update = params.__class__()
    for param in spec or []:
        if not param.startswith('%'):
            continue
        param_ = param[1:]
        assert param_ in ('include', 'manifest', 'params', 'recurse', 'path')
        params_update[param_] = spec[param]

    # Get updated parameters
    new_params = get_updated(params, params_update)

    obj = None
    # TODO: move all the tests harnessing outside, since it should be global
    # and not straight in here
    tests_passed = 0
    tests_errored = 0
    tests_failed = 0
    if toppath:
        # if points to a class we need to process.  If to a module, then depends
        # on recurse
        try:

            obj = get_object_from_path(toppath)

            if regex and not re.search(regex, toppath):
                raise SkipProcessing("regex")

            if 'include' in new_params and not new_params['include'](obj):
                raise SkipProcessing("%%include")

            lgr.debug("%s process!", toppath)

            if not outputdir:
                raise SkipProcessing("output_dir")

            # relative within hierarchy
            geardir = opj(*get_gear_dir(toppath))
            # full output path
            gearpath = opj(outputdir, geardir)

            if gear != "skip":
                try:
                    _ = create_gear(
                        obj,
                        gearpath,
                        # Additional fields for the
                        manifest_fields=new_params.get('manifest', {}),
                        build_docker=gear != "spec",  # For now
                        dummy=gear == 'dummy',
                        **new_params.get('params', {})
                    )
                    lgr.info("%s gear generated", toppath)
                except SyntaxError:
                    # some grave error -- blow
                    raise
                except Exception as e:
                    raise SkipProcessing(str(e))

            if run_tests != "skip":
                # TODO Move away and generalize
                testsdir = op.join(params['path'], 'tests', geardir)
                tests = glob(op.join(testsdir, 'test_*.yaml'))
                if not tests:
                    lgr.warning("TESTS: no tests were found")
                else:
                    lgr.info("TESTS: found %d tests", len(tests))
                for itest, test in enumerate(tests):
                    lgr.info(" test #%d: %s", itest+1, test)
                    # TODO: Redo all the below to just use one of the runners
                    # such as pytest internally
                    try:
                        testdir = tempfile.mkdtemp(prefix='gf_test-%d_' % itest)
                        _prepare(test, testdir)
                        if run_tests == 'native':
                            run_gear_native(gearpath, testdir)
                        elif run_tests == 'gear':
                            run_gear_docker("DOCKERIMAGENAME", testdir)
                        else:
                            raise ValueError(run_tests)

                        _check(test, testdir)
                        #  verify correspondence of # of files with target outputs
                        #  run the tests specified in tests.yaml if any, if none -
                        #  assume that they all must be identical
                    except Exception as exc:
                        lgr.error("  FAILED! %s", exc)
                        tests_errored += 1
                    finally:
                        # TODO shutil.rmtree(testdir)
                        import os
                        # os.system("ls -lRa %s/*" % testdir)
                        pass
                pass
        except SkipProcessing as exc:
            lgr.debug("SKIP(%s) %s", str(exc)[:100].replace('\n', ' '), toppath)

    paths_to_recurse = {
        path: path_spec
        for path, path_spec in spec.items()
        if not path.startswith('%')
    }

    if new_params['recurse'] and obj and ismodule(obj):
        # we were instructed to recurse so we will consider each path
        # which leads to either an object or another sub-module
        for attr in dir(obj):
            if attr.startswith('_'):
                continue
            subobj = getattr(obj, attr)
            subpath = '%s.%s' % (obj, attr)
            if attr not in paths_to_recurse and \
                (not ismodule(subobj) or
                    (ismodule(subobj) and
                     subobj.__name__.startswith(obj.__name__ + '.'))):
                    lgr.debug("Adding %s", subpath)
                    paths_to_recurse[attr] = {}   # no custom spec

    # after that we can traverse recursively for anything which is not %param
    for path, pathspec in paths_to_recurse.items():
        new_path = '.'.join([toppath, path]) if toppath else path

        _process(
                outputdir,
                spec=pathspec,
                regex=regex,
                run_tests=run_tests,
                gear=gear,
                toppath=new_path,
                actions=actions,
                params=new_params
        )


def run_gear_native(gearpath, testdir):
    # if we run natively, we have to copy manifest for the gear
    for f in [GEAR_RUN_FILENAME, GEAR_MANIFEST_FILENAME]:
        shutil.copy(op.join(gearpath, f), testdir)
    logsdir = op.join(testdir, '.gearificator', 'logs')
    if not op.exists(logsdir):
        os.makedirs(logsdir)
    # now just execute that gear in the directory
    log_stdout_path = op.join(logsdir, 'out')
    log_stderr_path = op.join(logsdir, 'err')
    with open(log_stdout_path, 'w') as log_stdout, \
            open(log_stderr_path, 'w') as log_stderr:
        exit_code = subprocess.call(
            './run', stdin=subprocess.PIPE,
            stdout=log_stdout,
            stderr=log_stderr,
            env=dict(os.environ, FLYWHEEL=testdir),
            cwd=testdir
        )
    if exit_code:
        raise RuntimeError(
            "Running gear under %s failed. Exit: %d"
            % (testdir, exit_code)
        )
    outs = [
        open(f).read() for f in [log_stdout_path, log_stderr_path]
    ]
    lgr.debug("Finished running gear with out=%s err=%s", *outs)
    return outs


# CLI

from .cli_base import cli


@cli.group("spec")
def grp():
    """Commands to manipulate the spec"""
    pass

@grp.command()
@click.option('--regex', help='Regular expression to process only the matching paths')
@click.option('--run-tests',
              type=click.Choice(['skip', 'native', 'gear']),
              help='Run tests if present.  "native" runs on the host and "gear" '
                   'via the dockerized gear')
@click.option('--gear', type=click.Choice(['spec', 'skip', 'dummy', 'build']),
              help="Either actuall build gear (dummy for testing UI or just spec "
                   "or full) or just skip (and possibly just do the tests "
                   "etc)")
# @click.option('--docker', type=click.Choice(['skip', 'dummy', 'build']),
#               help='Either actually build a docker image. "dummy" would generate'
#                    ' a minimalistic image useful for quick upload to test '
#                    'web UI')
@click.option('-o', '--outputdir', help='Output directory, to not place under gears/ alongside the spec')
@click.argument('inputdir') # , help='Directory with the spec.py and tests/, ...')
def process(
        inputdir,
        outputdir=None,  # if none provided -- nothing would be saved
        **kwargs
):
    """Load and process the spec

    The "spec" ATM is a directory with

    \b
    - spec.py
       file which prescribes how to traverse class hierarchy, and provides
       custom fields for gears
    - inputs/
       directory containing datasets used in tests
    - tests/
       directory mimicing produced gears/ directory hierarchy but providing
       per gear testname.yaml with specification of the test, and testname/
       directory with target outputs
    - gears/
       directory gets generated/used as the default `outputdir/`

    Recommended to keep inputs/ and tests output directories content under
    git-annex to minimize storage requirement etc
    """
    spec = load_spec(inputdir)
    if outputdir is None:
        outputdir = op.join(inputdir, 'gears')
    return _process(outputdir, spec=spec, **kwargs)