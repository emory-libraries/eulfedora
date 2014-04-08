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


from django.contrib.auth import views as authviews
from django.http import HttpResponse, Http404, HttpResponseBadRequest, \
    StreamingHttpResponse
from django.views.decorators.http import require_http_methods, condition

from eulfedora.util import RequestFailed
from eulfedora.server import Repository, FEDORA_PASSWORD_SESSION_KEY
from eulfedora.cryptutil import encrypt



class HttpResponseRangeNotSatisfiable(HttpResponseBadRequest):
    # error response for Requested range not satisfiable
    # from the spec:
    # Content-Range field with a byte-range- resp-spec of "*".
    # ??
    status_code = 416


def datastream_etag(request, pid, dsid, type=None, repo=None, **kwargs):
    '''Method suitable for use as an etag function with
    :class:`django.views.decorators.http.condition`.  Takes the same
    arguments as :meth:`~eulfedora.views.raw_datastream`.
    '''
    try:
        if repo is None:
            repo = Repository()
        get_obj_opts = {}
        if type is not None:
            get_obj_opts['type'] = type
        obj = repo.get_object(pid, **get_obj_opts)
        ds = obj.getDatastreamObject(dsid)
        if ds and ds.exists and ds.checksum_type != 'DISABLED':
            return ds.checksum
    except RequestFailed:
        pass

    return None


@condition(etag_func=datastream_etag)
@require_http_methods(['GET', 'HEAD'])
def raw_datastream(request, pid, dsid, type=None, repo=None, headers={}):
    '''View to display a raw datastream that belongs to a Fedora Object.
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
    '''

    if repo is None:
        repo = Repository()

    get_obj_opts = {}
    if type is not None:
        get_obj_opts['type'] = type
    obj = repo.get_object(pid, **get_obj_opts)

    range_request = True
    partial_request = False

    try:
        # NOTE: we could test that pid is actually the requested
        # obj.has_requisite_content_models but that would mean
        # an extra API call for every datastream but RELS-EXT
        # Leaving out for now, for efficiency

        ds = obj.getDatastreamObject(dsid)

        print 'if-range ? ', request.META.get('HTTP_IF_RANGE', None)
        if ds and ds.exists:
            # because retrieving the content is expensive and checking
            # headers can be useful, explicitly support HEAD requests
            if request.method == 'HEAD':
                content = ''

            elif request.META.get('HTTP_RANGE', None):
                rng = request.META['HTTP_RANGE']
                print 'setting range request=True'
                range_request = True
                print '** partial request = ', request.META['HTTP_RANGE']
                kind, numbers = rng.split('=')
                print 'kind = ', kind
                if kind != 'bytes':
                    return HttpResponseRangeNotSatisfiable()

                start, end = numbers.split('-')
                # NOTE: could potentially be complicated stuff like
                # this: 0-999,1002-9999,1-9999
                # assuming simple case of a single range
                start = int(start)
                if not end:
                    end = ds.info.size
                else:
                    end = int(end)
                print 'start %s end %s' % (start, end)

                # ignore requests where end is before start
                if end < start:
                    return HttpResponseRangeNotSatisfiable()

                # special case for bytes=0-
                if start == 0 and end == ds.info.size:
                    # set chunksize and end so range headers can be set on response
                    partial_length= ds.info.size

                    content = ds.get_chunked_content()

                # range with *NOT* full content requested
                elif start != 0 or end != ds.info.size:
                    partial_request = True
                    partial_length = end - start
                    # chunksize = min(end - start, 4096)
                    # sample chunk 370726-3005759
                    info = {}
                    content = get_range_content(ds, start, end, info)
                    print info

            else:
                # get the datastream content in chunks, to handle larger datastreams
                content = ds.get_chunked_content()
                # not using serialize(pretty=True) for XML/RDF datastreams, since
                # we actually want the raw datstream content.

            # NOTE: maybe only use streaming response over a certain size threshold?
            # response = HttpResponse(content, mimetype=ds.mimetype)
            response = StreamingHttpResponse(content, mimetype=ds.mimetype)

            # if we have a checksum, use it as an ETag
            # (but checksum not valid when sending partial content)
            if ds.checksum_type != 'DISABLED' and not partial_request:
                response['ETag'] = ds.checksum
                print '*** setting header: ETag=%s' % ds.checksum
            # TODO: set last-modified header also, if it is not oto costly
            # ds.created *may* be the creation date of this *version* of the datastream
            # so this might be what we want, at least in some cases - (needs to be confirmed)
            #response['Last-Modified'] = ds.created

            # Where available, set content length & MD5 checksum in response headers.
            # (but checksum not valid when sending partial content)
            if ds.checksum_type == 'MD5' and not partial_request:
                response['Content-MD5'] = ds.checksum
                print '*** setting header: Content-MD5=%s' % ds.checksum
            if ds.info.size and not range_request:
                response['Content-Length'] = ds.info.size
                print '*** setting header: Content-Length=%s' % ds.info.size
            if ds.info.size:
                response['Accept-Ranges'] = 'bytes'
                print '*** setting header: Accept-Ranges=bytes'
                # response['Content-Range'] = '0,%d/%d' % (ds.info.size, ds.info.size)

            # if partial request, status should be 206 (even for whole file?)
            if range_request:
            # if partial_request:
                print 'status code 206'
                response.status_code = 206
                response['Content-Length'] = partial_length
                print '*** setting header: Content-Length=%s' % partial_length
                response['Content-Range'] = 'bytes %d-%d/%d' % (start, end, ds.info.size)
                print '*** setting header: Content-Range=%s' % response['Content-Range']
                response['Content-Transfer-Encoding'] = 'binary'


            # set any user-specified headers that were passed in
            for header, val in headers.iteritems():
                response[header] = val

            return response
        else:
            raise Http404

    except RequestFailed as rf:
        # if object is not the speficied type or if either the object
        # or the requested datastream doesn't exist, 404
        if rf.code == 404 or \
            (type is not None and not obj.has_requisite_content_models) or \
                not getattr(obj, dsid).exists or not obj.exists :
            raise Http404

        # for anything else, re-raise & let Django's default 500 logic handle it
        raise


def get_range_content(ds, start, end, info):
    # don't go any bigger than our standard chunksize
    # NOTE: should there be a minimum also? e.g. don't want to chunk by 1
    # if we are grabbing content somewhere in the middle...
    if not end:
        end = ds.info.size
        print '*** setting end to ds.info.size'
    chunksize = min(end - start, 4096)
    # sample chunk 370726-3005759


    # FIXME: should be able to handle this case also
    # if start == 0 and end == '':
    #     # set chunksize and end so range headers can be set on response
    #     chunksize = end = ds.info.size
    #     print 'for 0- setting chunksize to %d' % chunksize
    #     content = ds.get_chunked_content()



    if end < start:
        print 'end is less than start!!'
    if end > ds.info.size:
        print 'end is more than datastream size!!'
        end = ds.info.size

    # TODO: need logic here to check that start is a multiple of chunksize
    # print 'chunksize = ', chunksize
    content_chunks = ds.get_chunked_content(chunksize=chunksize)
    # range val should be at least enough to get to the end of requested
    # print 'end/chunksize = %d' % (end / chunksize, )
    length = 0
    for i in range(end/chunksize + 10):
        chunk_start = chunksize  * i
        chunk_end = chunk_start + chunksize
        # print 'i = %d current chunk = %d-%d start = %d end = %d' % \
            # (i, chunk_start, chunk_end, start, end)

        content = content_chunks.next()
        if start == chunk_start:
            # print 'exact match between start and chunk, yielding content'
            yield content
            # FIXME: could be trimming end ?
        elif chunk_start < start < chunk_end:
            # print 'start is somewhere in chunk %d' % i
            # get the section of requested content at start index
            content = content[start-chunk_start:]
            # print 'yielding %d to end of chunk' % (start - chunk_start, )

            if chunk_start < end <= chunk_end:
                # print 'chunk end = %d end %d trim off %d' % (chunk_end, end, chunk_end - end)
                # print 'ends %d is inside chunk %d, limiting end to %d' % \
                     # (end, i, -(chunk_end - end))
                content = content[:-(chunk_end - end)]
                length += len(content)
                yield content

                # stop because we found the end
                break
            else:
                length += len(content)
                yield content

        elif chunk_start < end <= chunk_end:
            # print 'chunk end = %d end %d trim off %d' % (chunk_end, end, chunk_end - end)

            if end == ds.info.size:
                # print 'range end is ds end, no trim needed'
                yield content
                break

            # otherwise, trim based on *actual* size of current chunk,
            # since end chunk may not be fullsize
            real_chunksize = len(content)
            # print 'ends %d is inside chunk %d, limiting end to %d' % \
               # (end, i, -(chunk_start + real_chunksize - end))
            content = content[:-(chunk_start + real_chunksize - end)]

            length += len(content)
            print 'total content length yielded = %d' % length
            info['length'] = length
            yield content

            # stop because we found the end
            break

        elif chunk_start > start  and chunk_end < end:
            # print 'chunk is somewhere between start and end, yielding content'
            length += len(content)
            yield content





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
                            mimetype='text/xml')
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
