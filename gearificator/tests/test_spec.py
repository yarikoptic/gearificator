#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""

 COPYRIGHT: Yaroslav Halchenko 2014

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
import sys

from gearificator import get_logger
from gearificator.spec import get_updated, get_object_from_path

__author__ = 'yoh'
__license__ = 'MIT'


def test_get_updated():
    assert get_updated([{1: 2}], [2]) == [{1: 2}, 2]
    # scalar value overrides
    assert get_updated({1: 2, 3: 4}, {1: 3, 2: 3}) == {1: 3, 2: 3, 3: 4}
    # list get extended, dicts updated
    assert get_updated({1: [2], 3: {4: 1}}, {1: [3], 3: {1: 3}}) == {1: [2, 3], 3: {4: 1, 1: 3}}


def test_get_object_from_path():
    f = get_object_from_path
    assert f('sys.stdout') is sys.stdout
    assert f('gearificator.get_logger') is get_logger
    assert f('gearificator', 'get_logger') is get_logger