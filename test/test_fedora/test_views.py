#!/usr/bin/env python

# file test_fedora/test_views.py
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
import os
import unittest

# must be set before importing anything from django
os.environ['DJANGO_SETTINGS_MODULE'] = 'testsettings'

from django.conf import settings
from django.http import Http404
from django.template import Context, Template

from eulfedora.util import RequestFailed, PermissionDenied
from eulfedora.models import DigitalObject, Datastream, FileDatastream
from eulfedora.server import Repository, FEDORA_PASSWORD_SESSION_KEY
from eulfedora.views import raw_datastream, login_and_store_credentials_in_session, \
     datastream_etag
from eulfedora import cryptutil

from testcore import main

TEST_PIDSPACE = getattr(settings, 'FEDORA_PIDSPACE', 'testme')


class SimpleDigitalObject(DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:SimpleDjangoCModel' % TEST_PIDSPACE]
    # NOTE: distinguish from SimpleCModel in non-django fedora unit tests
    # and use configured pidspace for automatic clean-up

    # extend digital object with datastreams for testing
    text = Datastream("TEXT", "Text datastream", defaults={
            'mimetype': 'text/plain',
        })
    image = FileDatastream('IMAGE', 'managed binary image datastream', defaults={
                'mimetype': 'image/png'
        })

class FedoraViewsTest(unittest.TestCase):


    def setUp(self):
        # load test object to test views with
        repo = Repository()
        self.obj = repo.get_object(type=SimpleDigitalObject)
        self.obj.dc.content.title = 'test object for generic views'
        self.obj.text.content = 'sample plain-text content'
        img_file = os.path.join(settings.FEDORA_FIXTURES_DIR, 'test.png')
        self.obj.image.content = open(img_file)
        # force datastream checksums so we can test response headers
        for ds in [self.obj.dc, self.obj.rels_ext, self.obj.text, self.obj.image]:
            ds.checksum_type = 'MD5'
        self.obj.save()

    def tearDown(self):
        self.obj.api.purgeObject(self.obj.pid)

    def test_raw_datastream(self):
        rqst = Mock()
        rqst.method = 'GET'
        # return empty headers for ETag condition check
        rqst.META.get.return_value = None

        # DC
        response = raw_datastream(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream view of DC' \
                % (expected, got))
        expected, got = 'text/xml', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream view of DC' \
                % (expected, got))
        self.assertEqual(self.obj.dc.checksum, response['ETag'],
            'datastream checksum should be set as ETag header in the response')
        self.assertEqual(self.obj.dc.checksum, response['Content-MD5'])
        self.assert_('<dc:title>%s</dc:title>' % self.obj.dc.content.title in response.content)

        # RELS-EXT
        response = raw_datastream(rqst, self.obj.pid, 'RELS-EXT')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream view of RELS-EXT' \
                % (expected, got))
        expected, got = 'application/rdf+xml', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream view of RELS-EXT' \
                % (expected, got))

        # TEXT  (non-xml content)
        response = raw_datastream(rqst, self.obj.pid, 'TEXT')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream view of TEXT' \
                % (expected, got))
        expected, got = 'text/plain', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream view of TEXT' \
                % (expected, got))
        # non-xml datastreams should have content-md5 & content-length headers
        self.assertEqual(self.obj.text.checksum, response['Content-MD5'],
            'datastream checksum should be set as Content-MD5 header in the response')
        self.assertEqual(len(self.obj.text.content), int(response['Content-Length']))

        # IMAGE (binary content)
        response = raw_datastream(rqst, self.obj.pid, 'IMAGE')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream view of IMAGE' \
                % (expected, got))
        expected, got = 'image/png', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream view of IMAGE' \
                % (expected, got))
        # non-xml datastreams should have content-md5 & content-length headers
        self.assertEqual(self.obj.image.checksum, response['Content-MD5'],
            'datastream checksum should be set as Content-MD5 header in the response')
        self.assertTrue(response.has_header('Content-Length'),
            'content-length header should be set in the response for binary datastreams')

        # non-existent datastream should 404
        self.assertRaises(Http404, raw_datastream, rqst, self.obj.pid, 'BOGUS-DSID')        

        # non-existent record should 404
        self.assertRaises(Http404, raw_datastream, rqst, 'bogus-pid:1', 'DC')

        # check type handling?

        # set extra headers in the response
        extra_headers = {'Content-Disposition': 'attachment; filename=foo.txt'}
        response = raw_datastream(rqst, self.obj.pid, 'TEXT',
            headers=extra_headers)
        self.assertTrue(response.has_header('Content-Disposition'))
        self.assertEqual(response['Content-Disposition'], extra_headers['Content-Disposition'])


        # explicitly support GET and HEAD requests only
        rqst.method = 'POST'
        response = raw_datastream(rqst, self.obj.pid, 'DC')
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
            'Expected %s (Method not Allowed) but returned %s for POST to raw_datastream view' \
                % (expected, got))

        # HEAD request is handled internally, for efficiency
        rqst.method = 'HEAD'
        response = raw_datastream(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for HEAD request on raw_datastream view' \
                % (expected, got))
        self.assertEqual('', response.content)

    def test_datastream_etag(self):
        rqst = Mock()
        # DC
        etag = datastream_etag(rqst, self.obj.pid, 'DC')
        self.assertEqual(self.obj.dc.checksum, etag)

        # bogus dsid should not error
        etag = datastream_etag(rqst, self.obj.pid, 'bogus-datastream-id')
        self.assertEqual(None, etag)        

    def test_login_and_store_credentials_in_session(self):
        # only testing custom logic, which happens on POST
        # everything else is handled by django.contrib.auth
        mockrequest = Mock()
        mockrequest.method = 'POST'

        def not_logged_in(rqst):
            rqst.user.is_authenticated.return_value = False
            
        def set_logged_in(rqst):
            rqst.user.is_authenticated.return_value = True
            rqst.POST.get.return_value = "TEST_PASSWORD"
        
        # failed login
        with patch('eulfedora.views.authviews.login',
                   new=Mock(side_effect=not_logged_in)):
            mockrequest.session = dict()
            response = login_and_store_credentials_in_session(mockrequest)
            self.assert_(FEDORA_PASSWORD_SESSION_KEY not in mockrequest.session,
                         'user password for fedora should not be stored in session on failed login')

        # successful login
        with patch('eulfedora.views.authviews.login',
                   new=Mock(side_effect=set_logged_in)):
            response = login_and_store_credentials_in_session(mockrequest)
            self.assert_(FEDORA_PASSWORD_SESSION_KEY in mockrequest.session,
                         'user password for fedora should be stored in session on successful login')
            # test password stored in the mock request
            pwd = mockrequest.POST.get()
            # encrypted password stored in session
            sessionpwd = mockrequest.session[FEDORA_PASSWORD_SESSION_KEY]  
            self.assertNotEqual(pwd, sessionpwd,
                                'password should not be stored in the session without encryption')
            self.assertEqual(pwd, cryptutil.decrypt(sessionpwd),
                             'user password stored in session is encrypted')

if __name__ == '__main__':
    main()
