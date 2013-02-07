# file test_indexdata/test_views.py
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

import base64
from mock import patch
import unittest

from django.conf import settings
from django.http import Http404, HttpRequest
from django.utils import simplejson
from django.test.utils import override_settings

from eulfedora.indexdata.views import index_config, index_data
from eulfedora.models import DigitalObject, ContentModel
from eulfedora.server import Repository

from test.testsettings import FEDORA_PIDSPACE


class SimpleObject(DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:SimpleCModel' % FEDORA_PIDSPACE]


class LessSimpleDigitalObject(DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:SimpleDjangoCModel' % FEDORA_PIDSPACE,
                      'info:fedora/%s:OtherCModel' % FEDORA_PIDSPACE]

TEST_SOLR_URL = 'http://localhost:5555/'


@override_settings(SOLR_SERVER_URL=TEST_SOLR_URL)
class IndexDataViewsTest(unittest.TestCase):

    def setUp(self):
        #Creation of a HTTP request object for tests.
        self.request = HttpRequest
        self.request_ip = '127.0.0.1'
        self.request.META = {'REMOTE_ADDR': self.request_ip}
        self.pids = []

    def test_index_details(self):
        repo = Repository()
        for pid in self.pids:
            repo.purge_object(pid)

        #Test with no settings set.
        self.assertRaises(AttributeError, index_config, self.request)

        # Test with only the allowed SOLR url set.
        self.assertRaises(AttributeError, index_config, self.request)

        # Test with this IP not allowed to hit the service.
        #settings.EUL_INDEXER_ALLOWED_IPS = ['0.13.23.134']
        with override_settings(EUL_INDEXER_ALLOWED_IPS=['0.13.23.134']):
            response = index_config(self.request)
            expected, got = 403, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                % (expected, got))
            expected, got = 'text/html', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on indexdata/index_details view' \
                % (expected, got))

        # Test with this IP allowed to hit the view.
        with override_settings(EUL_INDEXER_ALLOWED_IPS=['0.13.23.134',
                                                    self.request_ip]):
            response = index_config(self.request)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                % (expected, got))
            expected, got = 'application/json', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on indexdata/index_details view' \
                % (expected, got))
            # load json content so we can inspect the result
            content = simplejson.loads(response.content)
            self.assertEqual(TEST_SOLR_URL, content['SOLR_URL'])
            print '** list of cmodels is ', content['CONTENT_MODELS']
            print '*** looking for ', SimpleObject.CONTENT_MODELS
            self.assert_(SimpleObject.CONTENT_MODELS in content['CONTENT_MODELS'])
            self.assert_(LessSimpleDigitalObject.CONTENT_MODELS in content['CONTENT_MODELS'])
            self.assert_(ContentModel.CONTENT_MODELS not in content['CONTENT_MODELS'],
               'Fedora system content models should not be included in indexed cmodels by default')

        # Test with the "ANY" setting for allowed IPs
        with override_settings(INDEXER_ALLOWED_IPS='ANY'):
            response = index_config(self.request)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                % (expected, got))

        # Test with 'EUL_INDEXER_CONTENT_MODELS' setting configured to override autodetect.
        with override_settings(EUL_INDEXER_CONTENT_MODELS=[
                ['content-model_1', 'content-model_2'], ['content-model_3']]):
            response = index_config(self.request)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for indexdata/index_details view' \
                % (expected, got))
            expected, got = 'application/json', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on indexdata/index_details view' \
                % (expected, got))
            # load json content so we can inspect the result
            content = simplejson.loads(response.content)
            self.assertEqual(settings.EUL_INDEXER_CONTENT_MODELS,
                content['CONTENT_MODELS'])

    def test_index_data(self):
        # create a test object for testing index data view
        repo = Repository()
        testobj = repo.get_object(type=SimpleObject)
        testobj.label = 'test object'
        testobj.owner = 'tester'
        testobj.save()
        self.pids.append(testobj.pid)

        # test with request IP not allowed to access the service
        with override_settings(EUL_INDEXER_ALLOWED_IPS=['0.13.23.134']):
            response = index_data(self.request, testobj.pid)
            expected, got = 403, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for index_data view with request IP not in configured list' \
                % (expected, got))

        # test with request IP allowed to hit the service
        with override_settings(EUL_INDEXER_ALLOWED_IPS=[self.request_ip]):
            response = index_data(self.request, testobj.pid)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for index_data view' \
                % (expected, got))
            expected, got = 'application/json', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on index_data view' \
                % (expected, got))
            response_data = simplejson.loads(response.content)
            self.assertEqual(testobj.index_data(), response_data,
               'Response content loaded from JSON should be equal to object indexdata')

            # test with basic auth
            testuser, testpass = 'testuser', 'testpass'
            token = base64.b64encode('%s:%s' % (testuser, testpass))
            self.request.META['HTTP_AUTHORIZATION'] = 'Basic %s' % token
            with patch('eulfedora.indexdata.views.TypeInferringRepository') as typerepo:
                typerepo.return_value.get_object.return_value.index_data.return_value = {}
                index_data(self.request, testobj.pid)
                typerepo.assert_called_with(username=testuser, password=testpass)

            # non-existent pid should generate a 404
            self.assertRaises(Http404, index_data, self.request, 'bogus:testpid')
