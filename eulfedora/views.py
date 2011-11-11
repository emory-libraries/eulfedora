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

    from django.conf.urls.defaults import *
    from eulfedora.views import raw_datastream

    urlpatterns = patterns('',
        url(r'^(?P<pid>[^/]+)/(?P<dsid>(MODS|RELS-EXT|DC))/$', raw_datastream),
    )

'''


from django.conf import settings
from django.contrib.auth import views as authviews
from django.http import HttpResponse, Http404
from django.views.decorators.http import require_http_methods, condition

from eulfedora.util import RequestFailed
from eulfedora.server import Repository, FEDORA_PASSWORD_SESSION_KEY
from eulfedora.cryptutil import encrypt


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
    try:
        # NOTE: we could test that pid is actually the requested
        # obj.has_requisite_content_models but that would mean
        # an extra API call for every datastream but RELS-EXT
        # Leaving out for now, for efficiency

        ds = obj.getDatastreamObject(dsid)
        
        if ds and ds.exists:
            # because retrieving the content is expensive and checking
            # headers can be useful, explicitly support HEAD requests
            if request.method == 'HEAD':
                content = ''
            else:
                # get the datastream content in chunks, to handle larger datastreams
                content = ds.get_chunked_content()
                # not using serialize(pretty=True) for XML/RDF datastreams, since
                # we actually want the raw datstream content.

            response = HttpResponse(content, mimetype=ds.mimetype)
            # if we have a checksum, use it as an ETag
            if ds.checksum_type != 'DISABLED':
                response['ETag'] = ds.checksum
            # TODO: set last-modified header also, if it is not too costly
            # ds.created *may* be the creation date of this *version* of the datastream
            # so this might be what we want, at least in some cases - (needs to be confirmed)
            #response['Last-Modified'] = ds.created
            
            # Where available, set content length & MD5 checksum in response headers.
            if ds.checksum_type == 'MD5':
                response['Content-MD5'] = ds.checksum
            if ds.info.size:
                response['Content-Length'] = ds.info.size

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
