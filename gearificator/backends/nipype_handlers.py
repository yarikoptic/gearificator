from collections import OrderedDict

import logging
lgr = logging.getLogger('gearificator.nipype')


# Handlers for various traits
# may be later TODO
MAPPING = {
    'default': 'default',
    'desc': 'description',
}
BASE_TYPES = {
    'unicode': 'string',
    'str': 'string',
    'int': 'integer',
    'float': 'number'
}


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
        if trait.default_kind == 'list' and trait.default == []:
            # just nothing for now
            # TODO raise NotImplementedError('list')
            pass
        elif trait.default_kind != 'value':
            # TODO raise NotImplementedError(trait.default_kind)
            lgr.warning("Not implemented for default_kind=%s",
                        trait.default_kind)
        else:
            trait_default = cast(trait.default)
            if trait_default:
                rec['default'] = trait_default

    if 'default' in rec:
        rec['description'] += ' [default=%s]' % rec['default']

    if not trait.mandatory and not rec.get('mandatory'):
        rec['optional'] = True

    # we might take care about those later on
    xor = trait.handler._metadata.get('xor', [])
    if xor:
        rec['xor'] = xor
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


def Range(trait, **kwargs):
    hdl = trait.handler
    rec = _get_rec(BASE_TYPES[hdl._validate.split('_')[0]], trait, **kwargs)
    if hdl._low is not None:
        rec['minimum'] = hdl._low
    if hdl._high is not None:
        rec['maximum'] = hdl._high
    if rec.get('default') is None and hdl.default_value is not None:
        rec['default'] = hdl.default_value
    return rec


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
        base_type = BASE_TYPES.get(base_type, base_type)
        rec = _get_rec(base_type, trait, **kwargs)
        # for inputs, we have 'base' to be 'file' or 'api-key', and then
        # type=enum={}
        rec['enum'] = values
    else:
        lgr.error("Cannot map multiple types %s to the base type", value_types)

    return rec


def List(trait, **kwargs):
    raise NotImplementedError("array - webui")  # Web UI still doesn't support them any sensible way
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


def Tuple(trait, **kwargs):
    rec = List(trait, **kwargs)
    # TODO: checks for uniform types and also annotate somewhere that we will need it as tuple
    return rec


def _MultiPath(orig_type, trait, **kwargs):
    # TODO: in general the idea is to allow for an Array here, typically
    # of files, but could be other things
    inner_trait_types = {t.trait_type for t in trait.inner_traits}
    if len(inner_trait_types) == 1:
        inner_type = inner_trait_types.pop()
        inner_name = inner_type.__class__.__name__
        #import pdb; pdb.set_trace()
        #print("INFO: %s %s" % (inner_type, inner_type.info()))
        # and we for now assume that one is enough!
        rec = {
            'File': File,
            'Str': Str
        }[inner_name](trait, **kwargs)
    else:
        raise ValueError("Do not know how to deal with %s having multiple types" % orig_type)
    return rec


def InputMultiPath(trait, **kwargs):
    return _MultiPath('InputMultiPath', trait, **kwargs)

# typically it is InputMultiPath (I guess it was all refactored in nipype) but since just bound to
# InputMultiObject we do not know that semantic unfortunately.
# That one in turn largely is a subclass of List with additional validation
def InputMultiObject(trait, **kwargs):
    return InputMultiPath(trait, **kwargs)


def OutputMultiPath(trait, **kwargs):
    return _MultiPath('OutputMultiPath', trait, **kwargs)


def OutputMultiObject(trait, **kwargs):
    return OutputMultiPath(trait, **kwargs)


def File(trait, **kwargs):
    rec = _get_rec(None, trait, **kwargs)
    rec['base'] = 'file'
    # rec['type'] = {'enum': ['nifti']}  # TODO: flexible types etc
    return rec


# nipype.interfaces.base
def Str(trait, **kwargs):
    rec = _get_rec('string', trait, **kwargs)
    # rec['base'] = 'string'  # File
    return rec


# discovered while going through fsl.epi
String = Str


def Directory(trait, **kwargs):
    # typically an output directory to be specified and even created
    # rec = _get_rec('string', trait, **kwargs)
    # if trait.handler.exists:
    #     # TODO: record the fact in custom fields that the output directory needs
    #     #       to be created if specified
    #     pass
    # return rec
    return File(trait, **kwargs)


def print_obj(o, include=lambda x: not x.startswith('_'), pref='', memo=None):
    if len(pref) > 3:
        print('----------------- CUT ---------------')
        # prevent inf
        return
    memo = memo or set()
    if isinstance(o, (int, float, str, bytes, list, tuple)):
        print(o)
        return
    for f in dir(o):
        if f == 'clone':
            continue
        if include(f):
            #print("%s: %s" % (f, print_obj(getattr(o, f))))

            v = getattr(o, f)
            note = ''
            descend = True
            if hasattr(v, '__call__'):
                try:
                    v = v()
                    note = "CALL(): "
                except Exception as exc:
                    note = "CALL ERROR" # : %s" % exc
                    descend = False
            print("%s%s: %s%s" % (pref, f, note, v))
            # if isinstance(v, (tuple, list)):
            #     for i in v:
            #         if id(i) in memo:
            #             print(pref + '--')
            #             continue
            #         memo.add(id(i))
            #         print_obj(i, include=include, pref=pref+' ', memo=memo)
            if descend and ('trait' in str(v)) and id(v) not in memo:
                memo.add(id(v))
                print_obj(v, include=include, pref=pref+' ', memo=memo)


def TraitCompound(trait, **kwargs):
    raise NotImplementedError("TraitCompound")
    handler = trait.handler
    subhandlers = handler.handlers
    subhandler_types = {t.__class__ for t in subhandlers}
    # For Either we should get special handling of various cases
    # - Bool, File() -- typical to signal output (can't check here
    #   since no name :-/.  But resort to bool just as a flag
    # - Tuples of various kinds . Could be a part of the list
    #    e.g. in antsRegistration to collect parameters of
    #    transformations for each stage
    if len(subhandler_types) == 1:
        # all the same type
        subhandler_type = subhandler_types.pop().__name__
        if subhandler_type == 'Tuple':
            # TODO: unfortunately those aren't just Tuple traits any more
            # grecs = [Tuple(t) for t in subhandlers]
            # Could not figure out any other way but just get the default
            # and their types
            tuple_types = [
                list({type(x).__name__ for x in subhandler.default_value})
                for subhandler in subhandlers
            ]
            tuple_lens = [
                len(subhandler.default_value) for subhandler in subhandlers
            ]
            all_types = None
            if max(len(t) for t in tuple_types) == 1:
                all_types = set(sum(tuple_types, []))
            if not (all_types and all_types.issubset({'int', 'float'})):
                raise NotImplementedError("Do not know how to handle such collections of tuples")
            if len(all_types) == 1:
                types = all_types.pop()
            else:
                types = "int or float"
            # 1. Generate the Tuple one giving a comment about the type of entries
            # 2. Record the knowledge about above types/# elements discovery
            #    into 'custom' somehow, so could be used for validation and
            #    reconstruction
            raise NotImplementedError()
    # - Trait, List(Trait) - ???
    # - Trait -- a few, I guess just for consistency. So we will
    #    just take the Trait
    # - StringConstant, File() - eg moving_image_masks
    #import pdb; pdb.set_trace()
    pass