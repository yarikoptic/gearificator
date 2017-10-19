#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""

 COPYRIGHT: Yaroslav Halchenko 2017

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

import json
from importlib import import_module

from gearificator.consts import (
    #MANIFEST_FIELD_BACKEND,
    MANIFEST_FIELD_INTERFACE,
)


def get_interface(manifest_file):
    """Load the manifest.json and extract the backend and interface
    """
    with open(manifest_file) as f:
        j = json.load(f)
    module_cls = j.get('custom', {}).get(MANIFEST_FIELD_INTERFACE, None)
    if not module_cls:
        raise ValueError("Did not find definition of the interface in %s"
                         % manifest_file)
    import pdb;
    # import that interface and return the object
    module_name, cls_name = module_cls.split(':')  # TODO: robustify
    #topmod, submod = module_name.split('.', 1)
    module = import_module(module_name)
    return getattr(module, cls_name)