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

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse

from eulfedora.models import DigitalObject, Datastream, FileDatastream
from eulfedora.server import Repository, FEDORA_PASSWORD_SESSION_KEY
from eulfedora.views import raw_datastream, login_and_store_credentials_in_session, \
     datastream_etag, datastream_lastmodified, raw_audit_trail, raw_datastream_old
from eulfedora import cryptutil
from eulfedora.util import force_bytes, force_text


TEST_PIDSPACE = getattr(settings, 'FEDORA_PIDSPACE', 'testme')


class SimpleDigitalObject(DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:SimpleDjangoCModel' % TEST_PIDSPACE]
    # NOTE: distinguish from SimpleCModel in non-django fedora unit tests
    # and use configured pidspace for automatic clean-up

    # extend digital object with datastreams for testing
    text = Datastream("TEXT", "Text datastream", defaults={
            'mimetype': 'text/plain',
            'versionable': True
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
        self.obj.image.content = open(img_file, mode='rb')
        # force datastream checksums so we can test response headers
        for ds in [self.obj.dc, self.obj.rels_ext, self.obj.text, self.obj.image]:
            ds.checksum_type = 'MD5'
        self.obj.save()

    def tearDown(self):
        self.obj.api.purgeObject(self.obj.pid)

    def test_raw_datastream_old(self):
        rqst = Mock()
        rqst.method = 'GET'
        # return empty headers for ETag condition check
        rqst.META = {}
        # rqst.META.get.return_value = None

        # DC
        response = raw_datastream_old(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        content = force_text(response.content)
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old view of DC' \
                % (expected, got))
        expected, got = 'text/xml', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream_old view of DC' \
                % (expected, got))
        self.assertEqual(self.obj.dc.checksum, response['ETag'],
            'datastream checksum should be set as ETag header in the response')
        self.assertEqual(self.obj.dc.checksum, response['Content-MD5'])
        self.assert_('<dc:title>%s</dc:title>' % self.obj.dc.content.title in content)

        # RELS-EXT
        response = raw_datastream_old(rqst, self.obj.pid, 'RELS-EXT')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old view of RELS-EXT' \
                % (expected, got))
        expected, got = 'application/rdf+xml', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream_old view of RELS-EXT' \
                % (expected, got))

        # TEXT  (non-xml content)
        response = raw_datastream_old(rqst, self.obj.pid, 'TEXT')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old view of TEXT' \
                % (expected, got))
        expected, got = 'text/plain', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream_old view of TEXT' \
                % (expected, got))
        # non-xml datastreams should have content-md5 & content-length headers
        self.assertEqual(self.obj.text.checksum, response['Content-MD5'],
            'datastream checksum should be set as Content-MD5 header in the response')
        self.assertEqual(len(self.obj.text.content), int(response['Content-Length']))

        # IMAGE (binary content)
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old view of IMAGE' \
                % (expected, got))
        expected, got = 'image/png', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_datastream_old view of IMAGE' \
                % (expected, got))
        # non-xml datastreams should have content-md5 & content-length headers
        self.assertEqual(self.obj.image.checksum, response['Content-MD5'],
            'datastream checksum should be set as Content-MD5 header in the response')
        self.assertTrue(response.has_header('Content-Length'),
            'content-length header should be set in the response for binary datastreams')
        self.assert_(isinstance(response, HttpResponse))

        # streaming
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE', streaming=True)
        self.assert_(isinstance(response, StreamingHttpResponse))

        # non-existent datastream should 404
        self.assertRaises(Http404, raw_datastream_old, rqst, self.obj.pid, 'BOGUS-DSID')

        # non-existent record should 404
        self.assertRaises(Http404, raw_datastream_old, rqst, 'bogus-pid:1', 'DC')

        # check type handling?

        # set extra headers in the response
        extra_headers = {'Content-Disposition': 'attachment; filename=foo.txt'}
        response = raw_datastream_old(rqst, self.obj.pid, 'TEXT',
            headers=extra_headers)
        self.assertTrue(response.has_header('Content-Disposition'))
        self.assertEqual(response['Content-Disposition'], extra_headers['Content-Disposition'])

        # explicitly support GET and HEAD requests only
        rqst.method = 'POST'
        response = raw_datastream_old(rqst, self.obj.pid, 'DC')
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
            'Expected %s (Method not Allowed) but returned %s for POST to raw_datastream view' \
                % (expected, got))

        # HEAD request is handled internally, for efficiency
        rqst.method = 'HEAD'
        response = raw_datastream_old(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for HEAD request on raw_datastream_old view' \
                % (expected, got))
        self.assertEqual(b'', response.content)

    def test_raw_datastream_old_range(self):
        # test http range requests
        rqst = Mock()
        rqst.method = 'GET'
        rqst.META = {}

        # use IMAGE for testing since it is binary content
        # set range header in the request; bytes=0- : entire datastream
        rqst.META['HTTP_RANGE'] = 'bytes=0-'

        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old range request' \
                % (expected, got))
        content = response.content
        self.assertEqual(self.obj.image.size, len(content),
            'range request of bytes=0- should return entire content (expected %d, got %d)' \
            % (self.obj.image.size, len(content)))
        self.assertEqual(self.obj.image.size, int(response['Content-Length']),
            'content-length header should be size of entire content (expected %d, got %d)' \
            % (self.obj.image.size, int(response['Content-Length'])))
        expected = 'bytes 0-%d/%d' % (self.obj.image.size - 1, self.obj.image.size)
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))
        del response

        # set range request for partial beginning content; bytes=0-150
        bytes_requested = 'bytes=0-150'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old range request' \
                % (expected, got))
        content_len = 150
        self.assertEqual(content_len, len(response.content),
            'range request of %s should return %d bytes, got %d' \
            % (bytes_requested, content_len, len(response.content)))
        self.assertEqual(content_len, int(response['Content-Length']),
            'content-length header should be set to partial size %d (got %d)' \
            % (content_len, int(response['Content-Length'])))
        expected = 'bytes 0-150/%d' % self.obj.image.size
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))

        # set range request for partial middle content; bytes=10-150
        bytes_requested = 'bytes=10-150'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old range request' \
                % (expected, got))
        content_len = 150 - 10
        self.assertEqual(content_len, len(response.content),
            'range request of %s should return %d bytes, got %d' \
            % (bytes_requested, content_len, len(response.content)))
        self.assertEqual(content_len, int(response['Content-Length']),
            'content-length header should be set to partial size %d (got %d)' \
            % (content_len, int(response['Content-Length'])))
        expected = 'bytes 10-150/%d' % self.obj.image.size
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))

        # set range request for partial end content; bytes=2000-3118
        bytes_requested = 'bytes=2000-3118'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old range request' \
                % (expected, got))
        content_len = 3118 - 2000
        self.assertEqual(content_len, len(response.content),
            'range request of %s should return %d bytes, got %d' \
            % (bytes_requested, content_len, len(response.content)))
        self.assertEqual(content_len, int(response['Content-Length']),
            'content-length header should be set to partial size %d (got %d)' \
            % (content_len, int(response['Content-Length'])))
        expected = 'bytes 2000-3118/%d' % self.obj.image.size
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))

        # invalid or unsupported ranges should return 416, range not satisfiable
        bytes_requested = 'bytes=10-9'  # start > end
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 416, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old invalid range request %s' \
                % (expected, got, bytes_requested))

        # complex ranges not yet supported
        bytes_requested = 'bytes=1-10,30-50'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 416, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old invalid range request %s' \
                % (expected, got, bytes_requested))

    def test_raw_datastream(self):
        # tests for new version of raw_datastream introduced in 1.5,
        # based on old raw_datastream tests

        rqst = Mock()
        rqst.method = 'GET'
        # return empty headers for ETag condition check
        rqst.META = {}

        # DC
        response = raw_datastream(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        content = b''.join(c for c in response.streaming_content)
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
        self.assert_('<dc:title>%s</dc:title>' % self.obj.dc.content.title in force_text(content))

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
        self.assert_(isinstance(response, StreamingHttpResponse))

        # non-existent datastream should 404
        self.assertRaises(Http404, raw_datastream, rqst, self.obj.pid, 'BOGUS-DSID')

        # non-existent record should 404
        self.assertRaises(Http404, raw_datastream, rqst, 'bogus-pid:1', 'DC')

        # set extra headers in the response
        extra_headers = {'Content-Disposition': 'attachment; filename=foo.txt'}
        response = raw_datastream_old(rqst, self.obj.pid, 'TEXT',
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

        # test HEAD request
        rqst.method = 'HEAD'
        response = raw_datastream(rqst, self.obj.pid, 'DC')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for HEAD request on raw_datastream view' \
                % (expected, got))
        self.assert_(isinstance(response, HttpResponse))
        self.assertEqual(b'', response.content)

        # test that range requests are passed through to fedora

        # use IMAGE for testing since it is binary content
        # set range header in the request; bytes=0- : entire datastream
        rqst.META['HTTP_RANGE'] = 'bytes=0-'
        rqst.method = 'GET'

        response = raw_datastream(rqst, self.obj.pid, 'IMAGE')
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream range request' \
                % (expected, got))
        content = b''.join(c for c in response.streaming_content)
        self.assertEqual(self.obj.image.size, len(content),
            'range request of bytes=0- should return entire content (expected %d, got %d)' \
            % (self.obj.image.size, len(content)))
        self.assertEqual(self.obj.image.size, int(response['Content-Length']),
            'content-length header should be size of entire content (expected %d, got %d)' \
            % (self.obj.image.size, int(response['Content-Length'])))
        expected = 'bytes 0-%d/%d' % (self.obj.image.size - 1, self.obj.image.size)
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))
        del response

        # set range request for partial beginning content; bytes=0-150
        bytes_requested = 'bytes=0-150'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream(rqst, self.obj.pid, 'IMAGE')
        expected, got = 206, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream range request' \
                % (expected, got))
        content_len = 151
        content = b''.join(c for c in response.streaming_content)
        self.assertEqual(content_len, len(content),
            'range request of %s should return %d bytes, got %d' \
            % (bytes_requested, content_len, len(content)))
        self.assertEqual(content_len, int(response['Content-Length']),
            'content-length header should be set to partial size %d (got %d)' \
            % (content_len, int(response['Content-Length'])))
        expected = 'bytes 0-150/%d' % self.obj.image.size
        self.assertEqual(expected, response['Content-Range'],
            'content range response header should indicate bytes returned (expected %s, got %s)' \
            % (expected, response['Content-Range']))

        # complex ranges not yet supported
        bytes_requested = 'bytes=1-10,30-50'
        rqst.META['HTTP_RANGE'] = bytes_requested
        response = raw_datastream_old(rqst, self.obj.pid, 'IMAGE',
                                  accept_range_request=True)
        expected, got = 416, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_datastream_old invalid range request %s' \
                % (expected, got, bytes_requested))

    def test_datastream_etag(self):
        rqst = Mock()
        rqst.META = {}
        # DC
        etag = datastream_etag(rqst, self.obj.pid, 'DC')
        self.assertEqual(self.obj.dc.checksum, etag)

        # bogus dsid should not error
        etag = datastream_etag(rqst, self.obj.pid, 'bogus-datastream-id')
        self.assertEqual(None, etag)

        # range request 1 to end should return etag
        rqst.META = {'HTTP_RANGE': 'bytes=1-'}
        etag = datastream_etag(rqst, self.obj.pid, 'DC')
        self.assertEqual(self.obj.dc.checksum, etag)


    def test_raw_datastream_version(self):
        rqst = Mock()
        rqst.method = 'GET'
        # return empty headers for ETag condition check
        rqst.META = {}

        self.obj.text.content = 'second version content'
        self.obj.text.save()

        # retrieve the view for each version and compare
        for version in self.obj.text.history().versions:

            # get the datastream version to compare with the response
            dsversion = self.obj.getDatastreamObject(self.obj.text.id,
                as_of_date=version.created)

            response = raw_datastream_old(rqst, self.obj.pid, self.obj.text.id,
                as_of_date=version.created)
            expected, got = 200, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for raw_datastream as of %s' \
                % (expected, got, version.created))
            expected, got = 'text/plain', response['Content-Type']
            self.assertEqual(expected, got,
                'Expected %s but returned %s for mimetype on raw_datastream as of %s' \
                    % (expected, got, version.created))
            # should use version-specific checksum and size
            self.assertEqual(dsversion.checksum, response['Content-MD5'],
                'datastream checksum should be set as Content-MD5 header in the response')
            self.assertEqual(dsversion.size, int(response['Content-Length']))
            # should retrieve appropriate version of the content
            self.assertEqual(dsversion.content, response.content)


    def test_datastream_lastmodified(self):
        rqst = Mock()
        rqst.META = {}
        # DC
        lastmod = datastream_lastmodified(rqst, self.obj.pid, 'DC')
        self.assertEqual(self.obj.dc.created, lastmod)

        # bogus dsid should not error
        lastmod = datastream_lastmodified(rqst, self.obj.pid, 'bogus-datastream-id')
        self.assertEqual(None, lastmod)

        # range request should not affect last modification time
        rqst.META = {'HTTP_RANGE': 'bytes=1-'}
        lastmod = datastream_lastmodified(rqst, self.obj.pid, 'DC')
        self.assertEqual(self.obj.dc.created, lastmod)

        # any other range request should still return last modification time
        rqst.META = {'HTTP_RANGE': 'bytes=300-500'}
        lastmod = datastream_lastmodified(rqst, self.obj.pid, 'DC', accept_range_request=True)
        self.assertEqual(self.obj.dc.created, lastmod)


    def test_raw_audit_trail(self):
        rqst = Mock()
        rqst.method = 'GET'

        # created with no ingest message = no audit trail
        self.assertRaises(Http404, raw_audit_trail, rqst, self.obj.pid)

        # modify object so it will have an audit trail
        self.obj.dc.content.title = 'audit this!'
        changelog = 'I just changed the title'
        self.obj.save(changelog)
        response = raw_audit_trail(rqst, self.obj.pid)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for raw_audit_trail' \
                % (expected, got))
        expected, got = 'text/xml', response['Content-Type']
        self.assertEqual(expected, got,
            'Expected %s but returned %s for mimetype on raw_audit_trail' \
                % (expected, got))
        self.assert_(b'<audit:auditTrail' in response.content)
        self.assert_(force_bytes('<audit:justification>%s</audit:justification>' % changelog)
                     in response.content)
        self.assert_('Last-Modified' in response)

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
            self.assertEqual(pwd, force_text(cryptutil.decrypt(sessionpwd)),
                             'user password stored in session is encrypted')
