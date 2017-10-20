from collections import OrderedDict

# Handlers for various traits
# may be later TODO
MAPPING = {
    'default': 'default',
    'desc': 'description',
}

import logging
lgr = logging.getLogger('gearificator.nipype')


# TODO: may be RF into a class with fancy getattr
# to avoid calling for default handling
def _get_rec(gear_type, trait, default=None, cast=lambda x: x, **kwargs):
    """Default record handling

    Parameters
    ----------
    cast: callable
      Callable (typically just a type, e.g. `int`) to convert
      value from possible str etc
    """
    rec = OrderedDict({'type': gear_type})
    rec.update(kwargs)
    rec['description'] = trait.desc if trait.dec else ''
    # rec['description'] = trait.get_help()
    if default is not None:
        rec['default'] = default
    elif trait.default is not None:
        if trait.default_kind != 'value':
            lgr.warning("Not implemented for default_kind=%s",
                        trait.default_kind)
        rec['default'] = cast(trait.default)

    if 'default' in rec:
        rec['description'] += ' [default=%s]' % rec['default']

    if not rec.get('mandatory'):
        rec['optional'] = True
    # Nipype
    #  requires?
    #  xor?  (so there is one or another, not both together)
    # Gear:
    #  base -- for enum?
    return rec


# traits.trait_types
def Int(trait, **kwargs):
    return _get_rec('integer', trait, **kwargs)


def Float(trait, **kwargs):
    return _get_rec('number', trait, **kwargs)


def Bool(trait, **kwargs):
    return _get_rec('boolean', trait, **kwargs)


def Enum(trait, **kwargs):
    # TODO could be of differing types may be, ATM need to dedue the type
    values = trait.handler.values
    # that is how it would have been for inputs
    # rec = _get_rec({'enum': values}, trait, **kwargs)

    # base???
    # TODO: could/sould we use trait.argstr ??
    value_types = set(map(type, values))
    if len(value_types) == 0:
        lgr.error("Enum without values??")
    elif len(value_types) == 1:
        value_type = value_types.pop()  # TODO - map etc
        base_type = value_type.__name__  # TODO -- deduce type
        # apply some mappings
        base_type = {
            'unicode': 'string'
        }.get(base_type, base_type)
        rec = _get_rec(base_type, trait, **kwargs)
        # for inputs, we have 'base' to be 'file' or 'api-key', and then
        # type=enum={}
        rec['enum'] = values
    else:
        lgr.error("Cannot map multiple types %s to the base type", value_types)

    return rec


def InputMultiPath(trait, **kwargs):
    #import pdb; pdb.set_trace()
    pass

# nipype.interfaces.base
def Str(trait, **kwargs):
    return _get_rec('string', trait, **kwargs)
