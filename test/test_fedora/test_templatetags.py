#!/usr/bin/env python

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

from StringIO import StringIO
import unittest

from django.template import Context, Template

from eulfedora.util import RequestFailed, PermissionDenied
from eulfedora.models import DigitalObject, Datastream, FileDatastream
from eulfedora.server import Repository

from testcore import main

class MockFedoraResponse(StringIO):
    # The simplest thing that can possibly look like a Fedora response to
    # eulcore.fedora.util
    def __init__(self, status=500, reason='Cuz I said so',
                 mimetype='text/plain', content=''):
        StringIO.__init__(self, content)
        self.status = status
        self.reason = reason
        self.mimetype = mimetype
        self.msg = self # for self.msg.gettype()

    def gettype(self):
        return self.mimetype

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

        response = MockFedoraResponse(status=401)
        test_obj._value = PermissionDenied(response) # force test_obj.value to fail
        val = t.render(ctx)
        self.assertEqual(val.strip(), 'permission fallback')

        response = MockFedoraResponse()
        test_obj._value = RequestFailed(response) # force test_obj.value to fail
        val = t.render(ctx)
        self.assertEqual(val.strip(), 'connection fallback')


if __name__ == '__main__':
    main()
