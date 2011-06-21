#!/usr/bin/env python

# file test_indexdata/test_webservice.py
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

from mock import Mock, patch
import unittest
import os

# must be set before importing anything from django
os.environ['DJANGO_SETTINGS_MODULE'] = 'testsettings'

from django.conf import settings
from django.http import Http404, HttpRequest

class WebserviceViewsTest(unittest.TestCase):

    def setUp(self):
        #Creation of a HTTP request object for tests.
        self.request = HttpRequest
        self.request.META = { 'REMOTE_ADDR': '127.0.0.1' }

    def test_index_details(self):
        #Mock object to return a fake CMODEL.
        mock_Digital_Object = Mock()
        mock_Attributes = Mock()
        mock_Attributes.CONTENT_MODELS = ['info/fedora:fakeCmodel']
        mock_Attributes.index = 'index'
        mock_Digital_Object.defined_types = {'Mocked Attribute': mock_Attributes}

        with patch('eulfedora.models.DigitalObject', mock_Digital_Object):
            from eulfedora.indexdata.views import index_details

            #Test with this IP not allowed to hit the service.
            settings.INDEXER_ALLOWED_IPS = ['0.13.23.134']
            settings.INDEX_SERVER_URL = 'http://localhost:5555'

            response = index_details(self.request)
            expected, got = 403, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                    % (expected, got))
            expected, got = 'text/html', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on indexdata/index_details view' \
                    % (expected, got))
        

            #Test with this IP allowed to hit the view.
            settings.INDEXER_ALLOWED_IPS = ['0.13.23.134', '127.0.0.1']
            response = index_details(self.request)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                    % (expected, got))
            expected, got = 'application/javascript', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on indexdata/index_details view' \
                    % (expected, got)) 
            self.assert_('INDEXER_URL' in response.content)
            self.assert_('http://localhost:5555' in response.content)
            self.assert_('info/fedora:fakeCmodel' in response.content)

            #Test with the "ANY" setting for allowed IPs
            settings.INDEXER_ALLOWED_IPS = 'ANY'
            response = index_details(self.request)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                    % (expected, got))

