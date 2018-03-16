"""Handle the spec prescribing how to traverse and create gear(s)
"""

import click
import re
import sys
import os.path as op
from os.path import join as opj
from inspect import ismodule
from itertools import chain
from gearificator import get_logger
from gearificator.main import create_gear

lgr = get_logger('spec')


def load_spec(path):
    # for now we have just one and we might redo it in yaml or alike
    from gearificator.specs.nipype import spec
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
            "Cannot figure out anything from empty path. Remaining attr=%s"
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


def process_spec(
        output,  # if none provided -- nothing would be saved
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
    output: str
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
        assert param_ in ('include', 'manifest', 'params', 'recurse')
        params_update[param_] = spec[param]

    # Get updated parameters
    new_params = get_updated(params, params_update)

    obj = None
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

            if not output:
                raise SkipProcessing("output_dir")

            # relative within hierarchy
            geardir = opj(*get_gear_dir(toppath))
            # full output path
            gearpath = opj(output, geardir)

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
                lgr.info("Running tests for %s", obj)
                # TODO
                # discover tests within input hierarchy
                # run each test by
                #  copy inputs
                #  create proper config.json
                #  execute test natively or via the gear
                #  verify correspondence of # of files with target outputs
                #  run the tests specified in tests.yaml if any, if none -
                #  assume that they all must be identical
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

        process_spec(
                output,
                spec=pathspec,
                regex=regex,
                run_tests=run_tests,
                gear=gear,
                toppath=new_path,
                actions=actions,
                params=new_params
        )


# CLI


@click.command()
@click.option('--regex', help='Regular expression to process only the matching paths')
@click.option('--pdb', help='Fall into pdb if errors out', is_flag=True)
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
@click.option('-l', '--log-level', help="Log level (TODO non-numeric values)",
              type=click.IntRange(1, 40), default=30)
#  @click.argument('spec', help='Input spec file')
@click.argument('output') #, help='Output directory.  Will be created if does not exist')
def main(
        output,  # if none provided -- nothing would be saved
        spec=None,  # TODO: make configurable
        log_level=30,
        pdb=False,
        **kwargs
):
    lgr.setLevel(log_level)
    if pdb:
        from .utils import setup_exceptionhook
        setup_exceptionhook()
    return process_spec(output, spec=load_spec(spec), **kwargs)


