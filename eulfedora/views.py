# file eulfedora/views.py
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

'''Generic, re-usable views for use with Fedora-based Django projects.
Intended to be analogous to `Django's generic views
<http://docs.djangoproject.com/en/1.2/topics/generic-views/>`_ .

Using these views (in the simpler cases) should be as easy as::

    from django.conf.urls import *
    from eulfedora.views import raw_datastream, raw_audit_trail

    urlpatterns = patterns('',
        url(r'^(?P<pid>[^/]+)/(?P<dsid>(MODS|RELS-EXT|DC))/$', raw_datastream),
        url(r'^(?P<pid>[^/]+)/AUDIT/$', raw_audit_trail),
    )

'''

from __future__ import unicode_literals
import logging

from django.contrib.auth import views as authviews
from django.http import HttpResponse, Http404, HttpResponseBadRequest, \
    StreamingHttpResponse
from django.views.decorators.http import require_http_methods, condition
from django.views.generic import View
import six

from eulfedora.cryptutil import encrypt
from eulfedora.server import Repository, FEDORA_PASSWORD_SESSION_KEY
from eulfedora.util import RequestFailed, parse_xml_object
from eulfedora.xml import DatastreamProfile


logger = logging.getLogger(__name__)


class HttpResponseRangeNotSatisfiable(HttpResponseBadRequest):
    '''Custom version of :class:`~django.http.HttpResponseBadRequest`
    to return a 416 response when a requested range cannot be satisfied.'''
    status_code = 416


def datastream_etag(request, pid, dsid, repo=None,
    as_of_date=None, **kwargs):
    '''Method suitable for use as an etag function with
    :class:`django.views.decorators.http.condition`.  Takes the same
    arguments as :meth:`~eulfedora.views.raw_datastream`.
    '''
    # if a range is requested and it is not for the entire file,
    # do *NOT* return an etag

    # NOTE: using api directly here instead of object/ds models
    # to avoid making unneeded api calls

    try:
        if repo is None:
            repo = Repository()
        resp = repo.api.getDatastream(pid, dsid, asOfDateTime=as_of_date)
        dsprofile = parse_xml_object(DatastreamProfile, resp.content, resp.url)
        if dsprofile and dsprofile.checksum_type != 'DISABLED':
            return dsprofile.checksum
    except RequestFailed:
        pass

    return None

def datastream_lastmodified(request, pid, dsid, repo=None,
    as_of_date=None, *args, **kwargs):
    '''Method suitable for use as a a last-modified function with
    :class:`django.views.decorators.http.condition`.  Takes basically
    the same arguments as :meth:`~eulfedora.views.raw_datastream`.
    '''
    try:
        if repo is None:
            repo = Repository()
        resp = repo.api.getDatastream(pid, dsid, asOfDateTime=as_of_date)
        dsprofile = parse_xml_object(DatastreamProfile, resp.content, resp.url)
        if dsprofile:
            return dsprofile.created
    except RequestFailed:
        pass


@condition(etag_func=datastream_etag, last_modified_func=datastream_lastmodified)
@require_http_methods(['GET', 'HEAD'])
def raw_datastream(request, pid, dsid, repo=None, headers=None,
       as_of_date=None):
    '''
    Access raw datastream content from a Fedora object.
    Returns :class:`~django.http.HttpResponse` for HEAD requests,
    :class:`~django.http.StreamingHttpResponse` for GET requests.  The
    headers and status code from Fedora response are set on the
    django response; any headers specified in the parameters will
    override Fedora headers.  If an HTTP_RANGE header is present on the
    request, it is passed through to Fedora.

    This view method is wrapped with ETag and last modified conditionals.

    :param request: HttpRequest
    :param pid: Fedora object PID
    :param dsid: datastream ID
    :param repo: :class:`~eulcore.django.fedora.server.Repository` instance to use,
        in case your application requires custom repository initialization (optional)
    :param headers: dictionary of additional headers to include in the response
    :param as_of_date: access a historical version of the datastream
    '''
    return _raw_datastream(request, pid, dsid, repo=repo, headers=headers,
       as_of_date=as_of_date)

def _raw_datastream(request, pid, dsid, repo=None, headers=None,
       as_of_date=None):
    '''Version of :meth:`raw_datastream` without conditionals, for use
    in class-based views or elsewhere.'''
    if repo is None:
        repo = Repository()

    # if a range request is present, pass it through to fedora
    rqst_headers = {}
    if 'HTTP_RANGE' in request.META:
        rqst_headers['RANGE'] = request.META['HTTP_RANGE']

    try:
        if request.method == 'HEAD':
            response = repo.api.getDatastreamDissemination(pid, dsid, asOfDateTime=as_of_date,
                head=True, rqst_headers=rqst_headers)
            dj_response = HttpResponse()
        else:
            response = repo.api.getDatastreamDissemination(pid, dsid, asOfDateTime=as_of_date,
                stream=True, rqst_headers=rqst_headers)
            dj_response = StreamingHttpResponse(response.iter_content(4096))
    except RequestFailed as rf:
        # if error is object not found, raise generic django 404
        if rf.code == 404:
            raise Http404

        # otherwise, raise the error
        raise

    # make sure django response code matches fedora code
    # e.g. error code or 206 partial content for range requests
    dj_response.status_code = response.status_code

    # copy fedora response headers to the django response
    resp_headers = response.headers
    # any headers passed in should take precedence
    if headers is not None:
        resp_headers.update(headers)
    # etag needn't always be content md5, but for fedora datastreams it is
    if 'ETag' in resp_headers:
        resp_headers['Content-MD5'] = resp_headers['ETag']

    for header, value in six.iteritems(resp_headers):
        dj_response[header] = value

    return dj_response


@condition(etag_func=datastream_etag)
@require_http_methods(['GET', 'HEAD'])
def raw_datastream_old(request, pid, dsid, type=None, repo=None, headers={},
                   accept_range_request=False, as_of_date=None,
                   streaming=False):
    '''
    .. NOTE::

        This version of :meth:`raw_datastream` is deprecated, and you
        should update to the new :meth:`raw_datastream`.  This version
        is still available if you are using a version of Fedora
        prior to 3.7 and need the additional functionality.

    View to display a raw datastream that belongs to a Fedora Object.
    Returns an :class:`~django.http.HttpResponse` with the response content
    populated with the content of the datastream.  The following HTTP headers
    may be included in all the responses:

    - Content-Type: mimetype of the datastream in Fedora
    - ETag: datastream checksum, as long as the checksum type is not 'DISABLED'

    The following HTTP headers may be set if the appropriate content is included
    in the datastream metadata:

    - Content-MD5: MD5 checksum of the datastream in Fedora, if available
    - Content-Length: size of the datastream in Fedora

    If either the datastream or object are not found, raises an
    :class:`~django.http.Http404` .  For any other errors (e.g., permission
    denied by Fedora), the exception is re-raised and should be handled elsewhere.

    :param request: HttpRequest
    :param pid: Fedora object PID
    :param dsid: datastream ID to be returned
    :param type: custom object type (should extend
        :class:`~eulcore.fedora.models.DigitalObject`) (optional)
    :param repo: :class:`~eulcore.django.fedora.server.Repository` instance to use,
        in case your application requires custom repository initialization (optional)
    :param headers: dictionary of additional headers to include in the response
    :param accept_range_request: enable HTTP Range requests (disabled by default)
    :param as_of_date: access a historical version of the datastream
    :param streaming: if True, response will be returned as an instance of
        :class:`django.http.StreamingHttpResponse` instead of
        :class:`django.http.HttpResponse`; intended for use with large
        datastreams, defaults to False.
    '''

    if repo is None:
        repo = Repository()

    get_obj_opts = {}
    if type is not None:
        get_obj_opts['type'] = type
    obj = repo.get_object(pid, **get_obj_opts)

    range_request = False
    partial_request = False

    try:
        # NOTE: we could test that pid is actually the requested
        # obj.has_requisite_content_models but that would mean
        # an extra API call for every datastream but RELS-EXT
        # Leaving out for now, for efficiency

        ds = obj.getDatastreamObject(dsid, as_of_date=as_of_date)

        if ds and ds.exists:
            # because retrieving the content is expensive and checking
            # headers can be useful, explicitly support HEAD requests
            if request.method == 'HEAD':
                content = ''

            elif accept_range_request and request.META.get('HTTP_RANGE', None) is not None:
                rng = request.META['HTTP_RANGE']
                logger.debug('HTTP Range request: %s' % rng)
                range_request = True
                kind, numbers = rng.split('=')
                if kind != 'bytes':
                    return HttpResponseRangeNotSatisfiable()

                try:
                    start, end = numbers.split('-')
                    # NOTE: could potentially be complicated stuff like
                    # this: 0-999,1002-9999,1-9999
                   # for now, only support the simple case of a single range
                except:
                    return HttpResponseRangeNotSatisfiable()

                start = int(start)
                if not end:
                    end = ds.info.size - 1
                else:
                    end = int(end)

                # ignore requests where end is before start
                if end < start:
                    return HttpResponseRangeNotSatisfiable()

                if start == end:  # safari sends this (weird?); don't 500
                    partial_length = 0
                    partial_request = True
                    content = ''

                # special case for bytes=0-
                elif start == 0 and end == (ds.info.size - 1):
                    # set chunksize and end so range headers can be set on response
                    # partial_length= ds.info.size
                    partial_length = end - start

                    content = ds.get_chunked_content()

                # range with *NOT* full content requested
                elif start != 0 or end != (ds.info.size - 1):
                    partial_request = True
                    partial_length = end - start
                    # chunksize = min(end - start, 4096)
                    # sample chunk 370726-3005759
                    content = get_range_content(ds, start, end)

            else:
                # get the datastream content in chunks, to handle larger datastreams
                content = ds.get_chunked_content()
                # not using serialize(pretty=True) for XML/RDF datastreams, since
                # we actually want the raw datastream content.

            http_response_class = HttpResponse
            if streaming:
                http_response_class = StreamingHttpResponse
            response = http_response_class(content, content_type=ds.mimetype)
            # NOTE: might want to use StreamingHttpResponse here, at least
            # over some size threshold or for range requests

            # if we have a checksum, use it as an ETag
            # (but checksum not valid when sending partial content)
            if ds.checksum_type != 'DISABLED' and not partial_request:
                response['ETag'] = ds.checksum
            # ds.created is the creation date of this *version* of the datastream,
            # so it is effectively our last-modified date
            response['Last-Modified'] = ds.created

            # Where available, set content length & MD5 checksum in response headers.
            # (but checksum not valid when sending partial content)
            if ds.checksum_type == 'MD5' and not partial_request:
                response['Content-MD5'] = ds.checksum
            if ds.info.size and not range_request:
                response['Content-Length'] = ds.info.size
            if ds.info.size and accept_range_request:
                response['Accept-Ranges'] = 'bytes'
                # response['Content-Range'] = '0,%d/%d' % (ds.info.size, ds.info.size)

            # if partial request, status should be 206 (even for whole file?)
            if range_request:
                response.status_code = 206
                if partial_request:
                    response['Content-Length'] = partial_length
                else:
                    response['Content-Length'] = ds.info.size
                cont_range = 'bytes %d-%d/%d' % (start, end, ds.info.size)
                response['Content-Range'] = cont_range
                logger.debug('Content-Length=%s Content-Range=%s' % \
                             (partial_length, cont_range))

            # set any user-specified headers that were passed in
            for header, val in six.iteritems(headers):
                response[header] = val

            # Fix for old Fedora data bug where the `Content-Length`
            # was -1. IF it is -1 we're just going to get rid of it.
            # Setting the value to an arbitrary value led to issues.
            if int(response['Content-Length']) < 0:
                del response['Content-Length']

            return response
        else:
            raise Http404

    except RequestFailed as rf:
        # if object is not the speficied type or if either the object
        # or the requested datastream doesn't exist, 404
        if rf.code == 404 or \
            (type is not None and not obj.has_requisite_content_models) or \
                not getattr(obj, dsid).exists or not obj.exists:
            raise Http404

        # for anything else, re-raise & let Django's default 500 logic handle it
        raise

def get_range_content(ds, start, end):
    '''Generator for range-requested datastream content.  Iterates over
    datastream content in chunks, and yields the chunks (or partial chunks)
    that are part of the requested range.'''
    if not end or end > ds.info.size:
        end = ds.info.size - 1
    chunksize = 4096

    content_chunks = ds.get_chunked_content(chunksize=chunksize)
    length = 0
    for i in range(int(end/chunksize) + 10):
        chunk_start = chunksize  * i
        chunk_end = chunk_start + chunksize

        # probably shouldn't run out of data, but in case data doesn't
        # match datastream metadata size in fedora...
        try:
            content = next(content_chunks)
        except StopIteration:
            break

        real_chunksize = len(content)

        if chunk_start <= start < chunk_end:
            # start of range is somewhere in the current chunk
            # get the section of requested content at start index
            content = content[start - chunk_start:]

            # range could also *end* in same chunk where it starts
            if chunk_start < end <= chunk_end:

                # trim based on *actual* size of current chunk (before any
                # start trim), since last chunk may not be fullsize
                end_trim = -(chunk_start + real_chunksize - end)
                if end_trim:
                    content = content[:end_trim]
                length += len(content)
                yield content

                # stop - hit the end of the range
                break
            else:
                length += len(content)
                yield content

        elif chunk_start < end <= chunk_end:
            # end of range is in this chunk; trim if necessary, then stop

            # trim based on *actual* size of current chunk (before any
            # start trimming), since last chunk may not be fullsize
            content = content[:-(chunk_start + real_chunksize - end)]

            length += len(content)
            yield content
            # stop - hit the end of the range
            break

        elif chunk_start > start  and chunk_end < end:
            # chunk is somewhere in the range of start - end
            length += len(content)
            yield content

    logger.debug('total content length returned is %d' % length)


@require_http_methods(['GET'])
def raw_audit_trail(request, pid, type=None, repo=None):
    '''View to display the raw xml audit trail for a Fedora Object.
    Returns an :class:`~django.http.HttpResponse` with the response content
    populated with the content of the audit trial.

    If the object is not found or does not have an audit trail, raises
    an :class:`~django.http.Http404` .  For any other errors (e.g.,
    permission denied by Fedora), the exception is not caught and
    should be handled elsewhere.

    :param request: HttpRequest
    :param pid: Fedora object PID
    :param repo: :class:`~eulcore.django.fedora.server.Repository` instance to use,
        in case your application requires custom repository initialization (optional)

    .. Note::

      Fedora does not make checksums, size, or other attributes
      available for the audit trail (since it is internal and not a
      true datastream), so the additional headers included in
      :meth:`raw_datastream` cannot be added here.

    '''

    if repo is None:
        repo = Repository()
    # no special options are *needed* to access audit trail, since it
    # is available on any DigitalObject; but a particular view may be
    # restricted to a certain type of object
    get_obj_opts = {}
    if type is not None:
        get_obj_opts['type'] = type
    obj = repo.get_object(pid, **get_obj_opts)
    # object exists and has a non-empty audit trail
    if obj.exists and obj.has_requisite_content_models and obj.audit_trail:
        response = HttpResponse(obj.audit_trail.serialize(),
                            content_type='text/xml')
        # audit trail is updated every time the object gets modified
        response['Last-Modified'] = obj.modified
        return response

    else:
        raise Http404

    # any other errors should be caught elsewhere


def login_and_store_credentials_in_session(request, *args, **kwargs):
    '''Custom login view.  Calls the standard Django authentication,
    but on successful login, stores encrypted user credentials in
    order to allow accessing the Fedora repository with the
    credentials of the currently-logged in user (e.g., when the
    application and Fedora share a common authentication system, such
    as LDAP).

    In order for :class:`~eulcore.django.fedora.server.Repository` to
    pick up user credentials, you must pass the request object in (so
    it will have access to the session).  Example::

        from eulcore.django.fedora.server import Repository

        def my_view(rqst):
            repo = Repository(request=rqst)


    Any arguments supported by :meth:`django.contrib.auth.views.login`
    can be specified and they will be passed along for the standard
    login functionality.

    **This is not a terribly secure.  Do NOT use this method unless
    you need the functionality.**

    '''
    response = authviews.login(request, *args, **kwargs)
    if request.method == "POST" and request.user.is_authenticated():
        # on successful login, encrypt and store user's password to use for fedora access
        request.session[FEDORA_PASSWORD_SESSION_KEY] = encrypt(request.POST.get('password'))
    return response



# class-based views

class RawDatastreamViewOld(View):
    '''Class-based view for serving out datastream content from Fedora.
    (View-based wrapper for :meth:`raw_datastream_old`.)
    '''
    #: subclass of DigitalObject, if needed
    object_type = None
    #: datastream id
    datastream_id = ''
    #: Enable range requests (default: False)
    accept_range_request = False
    #: url kwarg term for retrieving object pid (default: pid)
    pid_url_kwarg = 'pid'
    #: url kwarg term for retrieving date time, if used (default: date)
    as_of_date_url_kwarg = 'date'
    #: streaming response option (default: False)
    streaming = False
    #: Repository class to use, if needed
    repository_class = Repository
    #: extra http headers to include
    headers = {}

    @classmethod
    def etag(cls, request, *args, **kwargs):
        '''Class method to generate an ETag for use with
        conditional processing; calls :meth:`datastream_etag` with
        class configuration.'''
        pid = kwargs[cls.pid_url_kwarg]
        date = kwargs.get(cls.as_of_date_url_kwarg, None)
        return datastream_etag(request, pid, cls.datastream_id,
            type=cls.object_type, repo=cls.repository_class(request=request),
                    accept_range_request=cls.accept_range_request)

    @classmethod
    def last_modified(cls, request, *args, **kwargs):
        '''Class method to generate last-modified header for use with
        conditional processing; calls :meth:`datastream_lastmodified` with
        class configuration.'''
        pid = kwargs[cls.pid_url_kwarg]
        date = kwargs.get(cls.as_of_date_url_kwarg, None)
        return datastream_lastmodified(request, pid, cls.datastream_id,
            type=cls.object_type, repo=cls.repository_class(request=request),
                    accept_range_request=cls.accept_range_request)

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(RawDatastreamView, cls).as_view(**initkwargs)
        # wrap view with conditional decorator for etag/last-modified
        return condition(etag_func=cls.etag,
            last_modified_func=cls.last_modified)(view)

    def get_datastream_id(self):
        return self.datastream_id

    def get_repository(self):
        '''Initialize and return the configured repository class,
        passing in the current request.'''
        return self.repository_class(request=self.request)

    def get_headers(self):
        '''Return headers to be included when generating the datastream
        content response.  Default implementation is to return
        :attr:`headers`.'''
        return self.headers

    def head(self, request, *args, **kwargs):
        # raw_datastream method handles both head and get
        return self.get(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        pid = kwargs[self.pid_url_kwarg]
        date = kwargs.get(self.as_of_date_url_kwarg, None)
        return raw_datastream_old(request, pid, self.get_datastream_id(),
            type=self.object_type, repo=self.get_repository(),
            headers=self.get_headers(),
            accept_range_request=self.accept_range_request,
            as_of_date=date, streaming=self.streaming)


class RawDatastreamView(View):
    '''Class-based view for serving out datastream content from Fedora.
    (View-based wrapper for :meth:`raw_datastream`.)
    '''
    #: datastream id
    datastream_id = ''
    #: url kwarg term for retrieving object pid (default: pid)
    pid_url_kwarg = 'pid'
    #: url kwarg term for retrieving date time, if used (default: date)
    as_of_date_url_kwarg = 'date'
    #: Repository class to use, if needed
    repository_class = Repository
    #: extra http headers to include
    headers = {}

    @classmethod
    def etag(cls, request, *args, **kwargs):
        '''Class method to generate an ETag for use with
        conditional processing; calls :meth:`datastream_etag` with
        class configuration.'''
        pid = kwargs[cls.pid_url_kwarg]
        date = kwargs.get(cls.as_of_date_url_kwarg, None)
        return datastream_etag(request, pid, cls.datastream_id,
            repo=cls.repository_class(request=request),
            as_of_date=date)

    @classmethod
    def last_modified(cls, request, *args, **kwargs):
        '''Class method to generate last-modified header for use with
        conditional processing; calls :meth:`datastream_lastmodified` with
        class configuration.'''
        pid = kwargs[cls.pid_url_kwarg]
        date = kwargs.get(cls.as_of_date_url_kwarg, None)
        return datastream_lastmodified(request, pid, cls.datastream_id,
            repo=cls.repository_class(request=request),
            as_of_date=date)

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(RawDatastreamView, cls).as_view(**initkwargs)
        # wrap view with conditional decorator for etag/last-modified
        return condition(etag_func=cls.etag,
            last_modified_func=cls.last_modified)(view)

    def get_datastream_id(self):
        return self.datastream_id

    def get_repository(self):
        '''Initialize and return the configured repository class,
        passing in the current request.'''
        return self.repository_class(request=self.request)

    def get_headers(self):
        '''Return headers to be included when generating the datastream
        content response.  Default implementation is to return
        :attr:`headers`.'''
        return self.headers

    def head(self, request, *args, **kwargs):
        # raw_datastream method handles both head and get
        return self.get(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        pid = kwargs[self.pid_url_kwarg]
        date = kwargs.get(self.as_of_date_url_kwarg, None)
        return _raw_datastream(request, pid, self.get_datastream_id(),
            repo=self.get_repository(), headers=self.get_headers(),
            as_of_date=date)
