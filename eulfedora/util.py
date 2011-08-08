# file eulfedora/util.py
# 
#   Copyright 2010,2011 Emory University Libraries
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

from contextlib import contextmanager
from datetime import datetime
from dateutil.tz import tzutc
import httplib
import logging
import mimetypes
import random
import re
import string
import threading
import time
import urllib
from cStringIO import StringIO

from base64 import b64encode
from urlparse import urljoin, urlsplit

from rdflib import URIRef, Graph

from eulxml import xmlmap

from poster import streaminghttp

logger = logging.getLogger(__name__)

# NOTE: the multipart encoding below should be superceded by use of poster
# functions for posting multipart form data
# this code is a combination of:
#  - http://code.activestate.com/recipes/146306/
#  - urllib3.filepost.py    http://code.google.com/p/urllib3/

#ENCODE_TEMPLATE= """--%(boundary)s
#Content-Disposition: form-data; name="%(name)s"
#
#%(value)s
#""".replace('\n','\r\n')
#
#ENCODE_TEMPLATE_FILE = """--%(boundary)s
#Content-Disposition: form-data; name="%(name)s"; filename="%(filename)s"
#Content-Type: %(contenttype)s
#
#%(value)s
#--%(boundary)s--
#
#""".replace('\n','\r\n')
#
#def encode_multipart_formdata(fields, files):
#    """
#    fields is a sequence of (name, value) elements for regular form fields.
#    files is a sequence of (name, filename, value) elements for data to be uploaded as files
#    Return (content_type, body) ready for httplib.HTTP instance
#    """
#    BOUNDARY = generate_boundary()
#
#    body = ""
#
#    # NOTE: Every non-binary possibly-unicode variable must be casted to str()
#    # because if a unicode value pollutes the `body` string, then all of body
#    # will become unicode. Appending a binary file string to a unicode string
#    # will cast the binary data to unicode, which will raise an encoding
#    # exception. Long story short, we want to stick to plain strings.
#    # This is not ideal, but if anyone has a better method, I'd love to hear it.
#
#    for key, value in fields:
#        body += ENCODE_TEMPLATE % {
#                        'boundary': BOUNDARY,
#                        'name': str(key),
#                        'value': str(value)
#                    }
#    for (key, filename, value) in files:
#        body += ENCODE_TEMPLATE_FILE % {
#                    'boundary': BOUNDARY,
#                    'name': str(key),
#                    'value': str(value),
#                    'filename': str(filename),
#                    'contenttype': str(get_content_type(filename))
#                    }
#
#    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
#    return content_type, body
#
#def get_content_type(filename):
#    if filename:
#        guesses = mimetypes.guess_type(filename)
#        if guesses:
#            return guesses[0]
#    return 'application/octet-stream'

## generate a random boundary character string
#def generate_boundary():
#    return ''.join(random.choice(string.hexdigits[:16]) for x in range(32))
#

# utilities for making HTTP requests to fedora

def auth_headers(username, password):
    "Build HTTP basic authentication headers"
    if username and password:
        token = b64encode('%s:%s' % (username, password))
        return { 'Authorization': 'Basic ' + token }
    else:
        return {}

class RequestFailed(IOError):
    '''An exception representing an arbitrary error while trying to access a
    Fedora object or datastream.
    '''
    error_regex = re.compile('<pre>.*\n(.*)\n', re.MULTILINE)
    def __init__(self, response, content=None):
        # init params:
        #  response = HttpResponse with the error information
        #  content = optional content of the response body, if it needed to be read
        #            to determine what kind of exception to raise
        super(RequestFailed, self).__init__('%d %s' % (response.status, response.reason))
        self.code = response.status
        self.reason = response.reason
        if response.status == 500:
            # grab the response content if not passed in
            if content is None:
                content = response.read()
            # when Fedora gives a 500 error, it includes a stack-trace - pulling first line as detail
            # NOTE: this is likely to break if and when Fedora error responses change
            if response.msg.gettype() == 'text/plain':
                # for plain text, first line of stack-trace is first line of text
                self.detail = content.split('\n')[0]
            else:
                # for html, stack trace is wrapped with a <pre> tag; using regex to grab first line
                match = self.error_regex.findall(content)
                if len(match):
                    self.detail = match[0]

                    

class PermissionDenied(RequestFailed):
    '''An exception representing a permission error while trying to access a
    Fedora object or datastream.
    '''

class ChecksumMismatch(RequestFailed):
    '''Custom exception for a Checksum Mismatch error while trying to
    add or update a datastream on a Fedora object.
    '''
    error_label = 'Checksum Mismatch'
    def __init__(self, response, content):
        super(ChecksumMismatch, self).__init__(response, content)
        # the detail pulled out by  RequestFailed.__init__ includes extraneous
        # Fedora output; when possible, pull out just the checksum error details.
        # The error message will look something like this:
        #    javax.ws.rs.WebApplicationException: org.fcrepo.server.errors.ValidationException: Checksum Mismatch: f123b33254a1979638c23859aa364fa7
        # Use find/substring to pull out the checksum mismatch information
        if self.error_label in self.detail:
            self.detail = self.detail[self.detail.find(self.error_label):]
 
    def __str__(self):
        return self.detail


# custom exceptions?  fedora errors:
# fedora.server.errors.ObjectValidityException
# ObjectExistsException

class HttpServerConnection(object):
    def __init__(self, url):
        self.urlparts = urlsplit(url)
        # instead of stock httplib connection classes, use patched versions from poster module
        # - allows using a generator for content, in support of posting large files
        if self.urlparts.scheme == 'http':
            #self.connection_class = httplib.HTTPConnection
            self.connection_class = streaminghttp.StreamingHTTPConnection
        elif self.urlparts.scheme == 'https':
            #self.connection_class = httplib.HTTPSConnection
            self.connection_class = streaminghttp.StreamingHTTPSConnection
        
        self.thread_local = threading.local()

    def request(self, method, url, body=None, headers=None, throw_errors=True):
        response = self._connect_and_request(method, url, body, headers)

        # FIXME: handle 3xx
        if response.status >= 400 and throw_errors:
            # separate out 401 and 403 (permission errors) to enable
            # special handling in client code.
            if response.status in (401, 403):
                raise PermissionDenied(response)
            elif response.status == 500:
                # check response content to determine if this is a
                # ChecksumMismatch or a more generic error
                response_body = response.read()
                if 'ValidationException: Checksum Mismatch' in response_body:
                    raise ChecksumMismatch(response, response_body)
                else:
                    raise RequestFailed(response, response_body)
            else:
                raise RequestFailed(response)

        return response

    def _connect_and_request(self, method, url, body, headers):
        if getattr(self.thread_local, 'connection', None) is not None:
            try:
                # we're already connected. try to reuse it.
                return self._make_request(method, url, body, headers)
            except:
                # that didn't work. maybe the server disconnected on us.
                # reset the connection and try again.
                self._reset_connection()

        # either we didn't have a conn, or we had one but it failed
        self._get_connection()
        
        # now try sending the request again. this is the first time for this
        # new connection. if this fails, all hope is lost. just try to tidy
        # up a little then propagate the exception.
        try:
            return self._make_request(method, url, body, headers)
        except:
            self._reset_connection()
            raise

    def _get_connection(self):
        connection = self.connection_class(self.urlparts.hostname, self.urlparts.port)
        connection._http_vsn = 11
        connection._http_vsn_str = 'HTTP/1.1'
        self.thread_local.connection = connection

    def _reset_connection(self):
        self.thread_local.connection.close()
        self.thread_local.connection = None
        
    def _make_request(self, method, url, body, headers):
        start = time.time()
        url = self._sanitize_url(url)
        self.thread_local.connection.request(method, url, body, headers)
        response = self.thread_local.connection.getresponse()
        logger.debug('%s %s=>%d: %f sec' % (method, url,
            response.status, time.time() - start))
        return response

    def _sanitize_url(self, url):
        # a unicode url will surprisingly make httplib.Connection raise an
        # exception later if it tries to send a body that includes non-ascii
        # characters. coerce the url into ascii so that doesn't happen
        if isinstance(url, unicode):
            url = url.encode('utf-8')
        if not isinstance(url, basestring):
            url = str(url)
        # list derived from rfc 3987 "reserved" ebnf, plus "%" because we
        # fail without that.
        return urllib.quote(url, safe=":/?[]@!$&'()*+,;=%")

    @contextmanager
    def open(self, method, url, body=None, headers=None, throw_errors=True):
        response = self.request(method, url, body, headers, throw_errors)
        yield response
        response.read()


# wrap up all of our common aspects of accessing data over HTTP, from
# authentication to http/s switching to connection management to relative
# path resolving. sorta like urllib2 with extras.
class RelativeServerConnection(HttpServerConnection):
    def __init__(self, base_url):
        super(RelativeServerConnection, self).__init__(base_url)
        self.base_url = base_url

    def absurl(self, rel_url):
        return urljoin(self.base_url, rel_url)

    def open(self, method, rel_url, body=None, headers={}, throw_errors=True):
        abs_url = self.absurl(rel_url)
        super_open = super(RelativeServerConnection, self).open
        return super_open(method, abs_url, body, headers, throw_errors)

    def read(self, rel_url, data=None, headers={}, return_http_response=False):
        method = 'GET'
        if data is not None:
            method = 'POST'

        abs_url = self.absurl(rel_url)
        response = self.request(method, abs_url, data, headers)
        # if return_http_response is requested, return the response object
        if return_http_response:
            return response
        # otherwise, default behavior: return response contents and the requested url
        return response.read(), abs_url

    def __repr__(self):
        return '<%s %s >' % (self.__class__.__name__, self.base_url)

class AuthorizingServerConnection(object):
    def __init__(self, base, username=None, password=None):
        if isinstance(base, basestring):
            base = RelativeServerConnection(base)
        self.base = base
        self.base_url = base.base_url
        self.username = username
        self.password = password

    def _auth_headers(self):
        if self.username:
            token = b64encode('%s:%s' % (self.username, self.password))
            return { 'Authorization': 'Basic ' + token }
        else:
            return {}

    def open(self, method, rel_url, body=None, headers={}, throw_errors=True):
        headers = headers.copy()
        headers.update(self._auth_headers())
        return self.base.open(method, rel_url, body, headers, throw_errors)

    def read(self, rel_url, data=None, **kwargs):
        return self.base.read(rel_url, data, self._auth_headers(), **kwargs)


def parse_rdf(data, url, format=None):
    fobj = StringIO(data)
    id = URIRef(url)
    graph = Graph(identifier=id)
    if format is None:
        graph.parse(fobj)
    else:
        graph.parse(fobj, format=format)
    return graph

def parse_xml_object(cls, data, url):
    doc = xmlmap.parseString(data, url)
    return cls(doc)

def datetime_to_fedoratime(datetime):
    # format a date-time in a format fedora can handle
    # make sure time is in UTC, since the only time-zone notation Fedora seems able to handle is 'Z'
    utctime = datetime.astimezone(tzutc())      
    return utctime.strftime('%Y-%m-%dT%H:%M:%S') + '.%03d' % (utctime.microsecond/1000) + 'Z'


def fedoratime_to_datetime(rep):
    if rep.endswith('Z'):       
        rep = rep[:-1]      # strip Z for parsing
        tz = tzutc()
        # strptime creates a timezone-naive datetime
        dt = datetime.strptime(rep, '%Y-%m-%dT%H:%M:%S.%f')
        # use the generated time to create a timezone-aware
        return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond, tz)
    else:
        raise Exception("Cannot parse '%s' as a Fedora datetime" % rep)
