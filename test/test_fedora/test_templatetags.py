# file test_fedora/test_templatetags.py
#
#   Copyright 2011 Emory University Libraries
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import unittest
from mock import Mock

from django.template import Context, Template

from eulfedora.util import RequestFailed, PermissionDenied


class MockFedoraObject(object):
    # not even a close approximation, just something we can force to raise
    # interesting exceptions
    def __init__(self):
        self._value = 'sample text'

    def value(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class TemplateTagTest(unittest.TestCase):
    def test_parse_fedora_access(self):
        TEMPLATE_TEXT = """
            {% load fedora %}
            {% fedora_access %}
                {{ test_obj.value }}
            {% permission_denied %}
                permission fallback
            {% fedora_failed %}
                connection fallback
            {% end_fedora_access %}
        """
        t = Template(TEMPLATE_TEXT)
        test_obj = MockFedoraObject()
        ctx = Context({'test_obj': test_obj})

        val = t.render(ctx)
        self.assertEqual(val.strip(), 'sample text')

        response = Mock()
        response.status_code = 401
        response.headers = {'content-type': 'text/plain'}
        response.content = ''
        test_obj._value = PermissionDenied(response)  # force test_obj.value to fail
        val = t.render(ctx)
        self.assertEqual(val.strip(), 'permission fallback')

        response.status_code = 500
        test_obj._value = RequestFailed(response)  # force test_obj.value to fail
        val = t.render(ctx)
        self.assertEqual(val.strip(), 'connection fallback')
