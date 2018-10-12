"""Handle the spec prescribing how to traverse and create gear(s)
"""

import click
import re
import sys
import os.path as op
import shutil
import tempfile

from glob import glob
from os.path import join as opj
from inspect import ismodule
from itertools import chain

from .gear import (
    run_gear_native, run_gear_docker, create_gear, docker_push_gear,
    fw_upload_gear, copy_to_exchange
)
from . import get_logger
from .utils import import_module_from_file

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
    comps = filter(lambda p: p not in {"interfaces"},
                   path.split('.'))
    return op.join(comps)


def _process(
        outputdir,  # if none provided -- nothing would be saved
        spec=None,  # TODO: make configurable
        regex=None,
        run_tests=False,
        run_tests_regex=None,
        run_testsdir=None,
        gear=None,
        toppath=None,
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
    include: dict, optional
    manifest: dict, optional
    params: dict, optional
    gear: tuple of str
      What actions to perform to the gear, known ones: ...

    Returns
    -------
    None
    """
    gear = gear or ()
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

            if not obj.input_spec:
                raise SkipProcessing("no input spec")
            if not obj.output_spec:
                raise SkipProcessing("no output spec")


            lgr.debug("%s process!", toppath)

            if not outputdir:
                raise SkipProcessing("output_dir")

            # relative within hierarchy
            geardir = opj(*get_gear_dir(toppath))
            # full output path
            gearpath = opj(outputdir, geardir)

            gear_report = None
            if 'skip-build' not in gear:
                try:
                    gear_report = create_gear(
                        obj,
                        gearpath,
                        # Additional fields for the
                        manifest_fields=new_params.get('manifest', {}),
                        build_docker=gear != "spec",  # For now
                        dummy='dummy' in gear,
                        **new_params.get('params', {})
                    )
                    lgr.info("%s gear generated", toppath)
                except SyntaxError:
                    # some grave error -- blow
                    raise
                except NotImplementedError as exc:
                    lgr.warning("Skipping: %s", exc)
                    raise SkipProcessing("Not implemented yet")
                # except Exception as e:
                #     lgr.warning("ERROR happened: %s" % str(e))
                #     raise SkipProcessing("ERROR happened: %s" % str(e))

            if run_tests != "skip":
                # TODO Move away and generalize
                testspath = op.join(gearpath, 'tests')
                tests = glob(op.join(testspath, '*.yaml'))
                if not tests:
                    lgr.warning("TESTS: no tests were found")
                else:
                    lgr.info("TESTS: found %d tests", len(tests))
                for itest, test in enumerate(sorted(tests)):
                    testname = op.splitext(op.basename(test))[0]
                    testmsg = " test #%d: %s" % (itest+1, testname)
                    if run_tests_regex:
                        if not re.match(run_tests_regex, testname):
                            lgr.info(testmsg + " skipped")
                            continue
                    lgr.debug(" running " + testmsg)
                    # TODO: Redo all the below to just use one of the runners
                    # such as pytest internally
                    try:
                        if run_testsdir is not None:
                            testdir = tempfile.mkdtemp(prefix='gf_test-%d_' % itest)
                        else:
                            # create one under outputdir replicating testspath hierarchy

                            testdir = op.join(
                                params['path'], 'tests-run', geardir, testname)
                            if op.exists(testdir):
                                shutil.rmtree(testdir)

                        _prepare(test, testdir)

                        if run_tests == 'native':
                            run_gear_native(gearpath, testdir)
                        elif run_tests == 'gear':
                            if not gear_report:
                                raise ValueError("--gear option must not be 'skip'")
                            run_gear_docker(gear_report["docker_image"], testdir)
                        else:
                            raise ValueError(run_tests)

                        _check(test, testdir)
                        #  verify correspondence of # of files with target outputs
                        #  run the tests specified in tests.yaml if any, if none -
                        #  assume that they all must be identical
                        lgr.info(testmsg + " passed")
                    except Exception as exc:
                        lgr.error(testmsg + " FAILED: %s", exc)
                        tests_errored += 1
                    finally:
                        # TODO shutil.rmtree(testdir)
                        import os
                        # os.system("ls -lRa %s/*" % testdir)
                        pass
                pass
            if 'docker-push' in gear:
                if not gear_report:
                    raise ValueError("--gear option must not be 'skip'")
                docker_push_gear(gear_report['docker_image'])
            if 'fw-upload' in gear:
                fw_upload_gear(gearpath)
            if 'exchange' in gear:
                for exchange in glob(opj(outputdir, '..', 'exchanges', '*')):
                    copy_to_exchange(gearpath, exchange)
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
                run_tests_regex=run_tests_regex,
                gear=gear,
                toppath=new_path,
                params=new_params
        )


# CLI

from .cli_base import cli


@cli.group("spec")
def grp():
    """Commands to manipulate the spec"""
    pass

@grp.command()
@click.option('--regex', help='Regular expression to process only the matching paths')
@click.option('--run-tests',
              type=click.Choice(['skip', 'native', 'gear']), default='gear',
              help='Run tests if present.  "native" runs on the host and "gear" '
                   'via the dockerized gear')
@click.option('--run-tests-regex', help='Regular expression to run only the matching tests')
@click.option('--gear', type=click.Choice(
              ['spec', 'skip-build', 'dummy', 'build', 'docker-push', 'fw-upload', 'exchange']),
              multiple=True,
              help="Either actuall build gear (dummy for testing UI or just spec "
                   "or full) or just skip (and possibly just do the tests etc)")
# @click.option('--docker', type=click.Choice(['skip', 'dummy', 'build']),
#               help='Either actually build a docker image. "dummy" would generate'
#                    ' a minimalistic image useful for quick upload to test '
#                    'web UI')
@click.option('--run-testsdir', help='Directory, under which run the tests. If none provided, will be tests-runs/ under outputdir')
@click.option('-o', '--outputdir', help='Output directory, to not place under gears/ alongside the spec')
@click.argument('inputdir') # , help='Directory with the spec.py and tests/, ...')
def process(
        inputdir,
        outputdir=None,  # if none provided -- nothing would be saved
        run_testsdir=None,
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
    return _process(outputdir, spec=spec, run_testsdir=run_testsdir, **kwargs)
