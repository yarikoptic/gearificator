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
def _get_rec(gear_type, trait, cast=lambda x: x, **kwargs):
    """Default record handling

    Parameters
    ----------
    cast: callable
      Callable (typically just a type, e.g. `int`) to convert
      value from possible str etc
    """
    rec = OrderedDict({'type': gear_type})
    rec.update(kwargs)
    #if trait.desc:
    #    rec['description'] = trait.desc
    rec['description'] = trait.get_help()
    if trait.default is not None:
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
    # Gear:
    #  base -- for enum?
    return rec


# traits.trait_types
def Int(trait):
    return _get_rec('integer', trait)


def Float(trait):
    return _get_rec('number', trait)


def Bool(trait):
    return _get_rec('boolean', trait)


def Enum(trait):
    # TODO could be of differing types may be, ATM need to dedue the type
    values = trait.handler.values
    rec = _get_rec({'enum': values}, trait)
    # base???
    # TODO: could/sould we use trait.argstr ??
    value_types = set(map(type, values))
    if len(value_types) == 0:
        lgr.error("Enum without values??")
    elif len(value_types) == 1:
        value_type = value_types.pop()  # TODO - map etc
        rec['base'] = value_type.__name__  # TODO -- deduce type
    else:
        lgr.error("Cannot map multiple types %s to the base type", value_types)

    return rec


# nipype.interfaces.base
def Str(trait):
    return _get_rec('string', trait)
