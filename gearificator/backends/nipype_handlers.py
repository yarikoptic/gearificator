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
    rec = OrderedDict({'type': gear_type} if gear_type else {})
    rec.update(kwargs)
    rec['description'] = trait.desc if trait.desc else ''
    # rec['description'] = trait.get_help()
    if default is not None:
        rec['default'] = default
    elif trait.default is not None:
        if trait.default_kind != 'value':
            lgr.warning("Not implemented for default_kind=%s",
                        trait.default_kind)
        trait_default = cast(trait.default)
        if trait_default:
            rec['default'] = trait_default

    if 'default' in rec:
        rec['description'] += ' [default=%s]' % rec['default']

    if not trait.mandatory and not rec.get('mandatory'):
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
            'unicode': 'string',
            'int': 'integer',
        }.get(base_type, base_type)
        rec = _get_rec(base_type, trait, **kwargs)
        # for inputs, we have 'base' to be 'file' or 'api-key', and then
        # type=enum={}
        rec['enum'] = values
    else:
        lgr.error("Cannot map multiple types %s to the base type", value_types)

    return rec


def List(trait, **kwargs):
    if len(trait.inner_traits) != 1:
        raise ValueError(
            "Don't know yet how to treat a List trait with multiple types: %s"
            % trait.inner_traits
        )
    from .nipype import get_trait_handler
    inner_trait = trait.inner_traits[0]
    inner_handler, inner_handler_name = get_trait_handler(inner_trait)
    rec_inner = inner_handler(inner_trait)   # we care only about "type" here actually
    rec = _get_rec('array', trait, **kwargs)
    rec['items'] = {'type': rec_inner['type']}
    return rec


def InputMultiPath(trait, **kwargs):
    inner_trait_types = {t.trait_type for t in trait.inner_traits}
    if len(inner_trait_types) == 1:
        inner_type = inner_trait_types.pop()
        # and we for now assume that one is enough!
        rec = _get_rec(None, trait, **kwargs)
        rec['base'] = 'file'
        rec['type'] = {'enum': ['nifti']}  # TODO: flexible types etc
    else:
        raise ValueError("Do not know how to deal with InputMultiPath having multiple types")
    return rec

# nipype.interfaces.base
def Str(trait, **kwargs):
    return _get_rec('string', trait, **kwargs)
