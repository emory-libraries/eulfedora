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

from __future__ import unicode_literals
from datetime import datetime
from dateutil.tz import tzutc
import hashlib
import logging
import re

import six
from six.moves.builtins import bytes

import requests
from rdflib import URIRef, Graph
from six import BytesIO

from eulxml import xmlmap


logger = logging.getLogger(__name__)


def force_text(s, encoding='utf-8'):
    if six.PY3:
        if isinstance(s, bytes):
            s = six.text_type(s, encoding)
        else:
            s = six.text_type(s)
    else:
        s = six.text_type(bytes(s), encoding)

    return s


def force_bytes(s, encoding='utf-8'):
    if isinstance(s, bytes):
        if encoding == 'utf-8':
            return s
        else:
            return s.decode('utf-8').encode(encoding)

    if not isinstance(s, six.string_types):
        if six.PY3:
            return six.text_type(s).encode(encoding)
        else:
            return bytes(s)
    else:
        return s.encode(encoding)


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
        super(RequestFailed, self).__init__('%d %s' % (response.status_code, response.text))
        self.code = response.status_code
        self.reason = response.text
        if response.status_code == requests.codes.server_error:
            # grab the response content if not passed in
            if content is None:
                content = response.text
            content = force_text(content)
            # when Fedora gives a 500 error, it includes a stack-trace - pulling first line as detail
            # NOTE: this is likely to break if and when Fedora error responses change
            if 'content-type' in response.headers and response.headers['content-type'] == 'text/plain':
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
    def __init__(self, response):
        super(ChecksumMismatch, self).__init__(response)
        # the detail pulled out by  RequestFailed.__init__ includes extraneous
        # Fedora output; when possible, pull out just the checksum error details.
        # The error message will look something like this:
        #    javax.ws.rs.WebApplicationException: org.fcrepo.server.errors.ValidationException: Checksum Mismatch: f123b33254a1979638c23859aa364fa7
        # Use find/substring to pull out the checksum mismatch information
        if self.error_label in self.detail:
            self.detail = self.detail[self.detail.find(self.error_label):]

    def __str__(self):
        return self.detail


def parse_rdf(data, url, format=None):
    fobj = BytesIO(data)
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

def file_md5sum(filename):
    '''Calculate and returns an MD5 checksum for the specified file.  Any file
    errors (non-existent file, read error, etc.) are not handled here but should
    be caught where this method is called.

    :param filename: full path to the file for which a checksum should be calculated
    :returns: hex-digest formatted MD5 checksum as a string
    '''
    # duplicated from keep.common.utils
    # possibly at some point this should be moved to a common codebase/library
    md5 = hashlib.md5()
    with open(filename, 'rb') as filedata:
        for chunk in iter(lambda: filedata.read(128 * md5.block_size), b''):
            md5.update(chunk)
    return md5.hexdigest()

def md5sum(content):
    '''Calculate and returns an MD5 checksum for the specified content.

    :param content: text content
    :returns: hex-digest formatted MD5 checksum as a string
    '''
    md5 = hashlib.md5()
    md5.update(force_bytes(content))
    return md5.hexdigest()


class ReadableIterator(object):
    '''Adaptor to allow an iterable with known size to be treated like
    a file-like object so it can be uploaded via requests/requests-toolbelt.
    Expects data as bytes, not string data.
    '''
    # adapted from "some_magic_adaptor" here:
    # http://stackoverflow.com/questions/12593576/adapt-an-iterator-to-behave-like-a-file-like-object-in-python

    def __init__(self, iterable, size):
        self.iterable = iterable
        self.next_chunk = b''
        self.size = size
        self.amount_read = 0

    def __len__(self):
        # requests toolbelt expects the length of the content to be
        # the amount that has not yet been read (which is how it
        # determines when to stop reading), not the total size
        # of the content
        return self.size - self.amount_read

    def grow_chunk(self):
        self.next_chunk = self.next_chunk + force_bytes(six.next(self.iterable))

    def read(self, size):
        if self.next_chunk == None:
          return None
        try:
          while len(self.next_chunk) < size:
            self.grow_chunk()
          data = self.next_chunk[:size]
          self.next_chunk = self.next_chunk[size:]
          self.amount_read += len(data)
          return data
        except StopIteration:
          data = self.next_chunk
          self.next_chunk = None
          self.amount_read += len(data)
          return data

try:
    from django.views import debug

    class SafeExceptionReporterFilter(debug.SafeExceptionReporterFilter):
        '''Under certain circumstances, an exception made when actually
        making a request to Fedora can result in the auth username and password
        being included in the stack trace.  This filter suppresses the
        password.  To enable this filter, configure it in your Django
        settings like this::

            DEFAULT_EXCEPTION_REPORTER_FILTER = 'eulfedora.util.SafeExceptionReporterFilter'

        '''

        def get_traceback_frame_variables(self, request, tb_frame):
            # let the parent class filter everything first
            cleansed = super(SafeExceptionReporterFilter, self) \
                .get_traceback_frame_variables(request, tb_frame)

            return self.filter_cleansed(cleansed)

        def filter_cleansed(self, cleansed):
            # iterate through the stack trace variables that have
            # already been cleaned by the django filter to check for
            # request auth parameters set in api._make_request
            for varname, values in cleansed:
                if varname == 'rqst_options' and 'auth' in values:
                    # auth is a tuple, which can't be edited,
                    # so cnstruct a new one with subsitute value
                    # instead of the actual password
                    cleansed_auth = (values['auth'][0],
                                     debug.CLEANSED_SUBSTITUTE)
                    values['auth'] = cleansed_auth
            return cleansed


except ImportError:
    pass
