"""Utilities for validation of the generated files etc"""
import json
import jsonschema
from os.path import (
    join as opj, pardir, dirname
)
import gearificator
import gearificator.borrowed
from gearificator.utils import load_json

# TODO: just refactor into classes


class Manifest(object):

    type = 'json'
    schema = opj(dirname(gearificator.borrowed.__file__), 'manifest.schema.json')


def validate(cls, path):
    if cls.type == 'json':
        schema = load_json(cls.schema, must_exist=True)
        content = load_json(path, must_exist=True)
        jsonschema.validate(content, schema)  # will throw exceptions if smth is not rightr
    else:
        raise ValueError("nothing else ATM")


def validate_manifest(path):
    """Validate gears manifest.json"""
    validate(Manifest, path)