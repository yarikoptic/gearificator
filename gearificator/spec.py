"""Handle the spec prescribing how to traverse and create gear(s)
"""

import re
import sys
from os.path import join as opj
from inspect import ismodule
from itertools import chain
from gearificator import get_logger
from gearificator.main import create_gear

from gearificator.consts import (
    DOCKER_IMAGE_REPO,
    MANIFEST_FILENAME,
    MANIFEST_CUSTOM_SECTION,
    MANIFEST_CUSTOM_INTERFACE,
    MANIFEST_CUSTOM_OUTPUTS,
)
from gearificator.exceptions import UnknownBackend

from gearificator.run import load_interface_from_manifest
from gearificator.validator import validate_manifest

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


def test_get_updated():
    assert get_updated([{1: 2}], [2]) == [{1: 2}, 2]
    # scalar value overrides
    assert get_updated({1: 2, 3: 4}, {1: 3, 2: 3}) == {1: 3, 2: 3, 3: 4}
    # list get extended, dicts updated
    assert get_updated({1: [2], 3: {4: 1}}, {1: [3], 3: {1: 3}}) == {1: [2, 3], 3: {4: 1, 1: 3}}


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
        try:
            path_split = path.rsplit('.', 1)
            topmod = None if len(path_split) == 1 else path_split[0]
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


def test_get_object_from_path():
    f = get_object_from_path
    assert f('sys.stdout') is sys.stdout
    assert f('gearificator.get_logger') is get_logger
    assert f('gearificator', 'get_logger') is get_logger


class SkipProcessing(Exception):
    pass


def process_spec(
        spec=None,
        output_dir=None,  # if none provided -- nothing would be saved
        toppath=None,
        actions=None,
        regex=None,
        params={
            'recurse': False
        }
):
    """

    Parameters
    ----------
    spec: dict
    output_dir: str
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

            if not output_dir:
                raise SkipProcessing("output_dir")

            geardir = opj(output_dir, toppath)

            try:
                gear_spec = create_gear(
                    obj,
                    geardir,
                    # Additional fields for the
                    manifest_fields=new_params.get('manifest', {}),
                    build_docker=False,  # For now
                    **new_params.get('params', {})
                )
                lgr.info("%s gear generated", toppath)
            except Exception as e:
                raise SkipProcessing(str(e))
        except SkipProcessing as exc:
            lgr.debug("SKIP(%s) %s", str(exc)[:100].replace('\n', ' '), toppath)
    else:
        obj = None

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
                (not ismodule(subobj) or \
                    (ismodule(subobj) and
                     subobj.__name__.startswith(obj.__name__ + '.'))):
                    lgr.debug("Adding %s", subpath)
                    paths_to_recurse[attr] = {}   # no custom spec

    # after that we can traverse recursively for anything which is not %param
    for path, pathspec in paths_to_recurse.items():
        new_path = '.'.join([toppath, path]) if toppath else path

        process_spec(
                pathspec,
                output_dir,
                toppath=new_path,
                actions=actions,
                regex=regex,
                params=new_params
        )


if __name__ == '__main__':
    process_spec(
        load_spec(None)
        , output_dir='/tmp/gearificator-output'
      #  , regex=".*\.BET"
       , regex=".*\.Dcm2Niix"
    )