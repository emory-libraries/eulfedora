# file eulfedora/indexdata/views.py
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

"""
Generic, re-usable views for use with Fedora-based Django
projects. These views expose data intended for use with
:mod:`eulindexer`. These views currently return data in JSON form.

Projects that use this module should include the following settings in their
``settings.py``::

    # Index server url. In this example case, we are wish to push data to a Solr instance.
    SOLR_SERVER_URL = "http://localhost:8983/solr/"
    # IPs that will be allowed to access the indexdata views
    EUL_INDEXER_ALLOWED_IPS = "ANY" #Or put in a list such as ("127.0.0.1", "127.0.0.2")
    
    # OPTIONAL SETTING: A list of lists of content models you want this application to index.
    # If this setting is missing, the code will automatically detect all content
    # models the application is using. In this example, it will index items with BOTH
    # content-model_1 and content-model_2 as well as those that have just content-model_3.
    EUL_INDEXER_CONTENT_MODELS = "[['content-model_1', 'content-model_2'], ['content-model_3']]"

To use these views in your :mod:`eulfedora` -based application, make
sure that ``eulfedora`` is included in INSTALLED_APPS in your ``settings.py``::

    INSTALLED_APPS = (
        'eulfedora'
        # Additional installed applications here,
    )

And then bind the indexdata views to a url in your application
``urls.py``::
        
    from django.conf.urls.defaults import *

    urlpatterns = patterns('',
        url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
        # Additional url patterns here,
    )


An example Solr schema with fields defined for all the index values
exposed in the default
:meth:`~eulfedora.models.DigitalObject.index_data` method is included
with :mod:`eulfedora.indexdata` to be used as a starting point for
applications.

----

"""

import logging
import os
import json
from django.utils import simplejson
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseForbidden, \
    HttpResponseBadRequest

from eulfedora.models import DigitalObject
from eulfedora.server import TypeInferringRepository
from eulfedora.util import RequestFailed


logger = logging.getLogger(__name__)

def index_config(request):
    '''This view returns the index configuration of the current
    application as JSON.  Currently, this consists of a Solr index url
    and the Fedora content models that this application expects to index.

    .. Note::
    
       By default, Fedora system content models (such as
       ``fedora-system:ContentModel-3.0``) are excluded.  Any
       application that actually wants to index such objects will need
       to customize this view to include them.
    '''
    #Ensure permission to this resource is allowed. Currently based on IP only.
    if _permission_denied_check(request):
        return HttpResponseForbidden('Access to this web service was denied.', content_type='text/html')

    content_list = getattr(settings, 'EUL_INDEXER_CONTENT_MODELS', [])

    # Generate an automatic list of lists of content models (one list for each defined type)
    # if no content model settings exist
    if not content_list:
        for cls in DigitalObject.defined_types.itervalues():
            # by default, Fedora system content models are excluded
            content_group = [model for model in getattr(cls, 'CONTENT_MODELS', [])
                             if not model.startswith('info:fedora/fedora-system:')]
            # if the group of content models is not empty, add it to the list
            if content_group:
                content_list.append(content_group)

    response = {
        'CONTENT_MODELS': content_list,
        'SOLR_URL': settings.SOLR_SERVER_URL
    }

    return HttpResponse(simplejson.dumps(response), content_type='application/json')

def index_data(request, id, repo=None):
    '''Return the fields and values to be indexed for a single object
    as JSON.  Index content is generated via
    :meth:`eulfedora.models.DigitalObject.index_data`.

    :param id: id of the object to be indexed; in this case a Fedora pid
    '''

    #Ensure permission to this resource is allowed. Currently based on IP only.
    if _permission_denied_check(request):
        return HttpResponseForbidden('Access to this web service was denied.', content_type='text/html')

    if repo is None:
        repo_opts = {}
        # if credentials are specified via Basic Auth, use them for Fedora access
        auth_info = request.META.get('HTTP_AUTHORIZATION', None)
        basic = 'Basic '
        if auth_info and auth_info.startswith(basic):
            basic_info = auth_info[len(basic):]
            u, p = basic_info.decode('base64').split(':')
            repo_opts.update({'username': u, 'password': p})
            
        repo = TypeInferringRepository(**repo_opts)
    try:
        obj = repo.get_object(id)
        return HttpResponse(simplejson.dumps(obj.index_data()),
                            content_type='application/json')
    except RequestFailed:
        # for now, treat any failure getting the object from Fedora as a 404
        # (could also potentially be a permission error)
        raise Http404

def _permission_denied_check(request):
    '''Internal function to verify that access to this webservice is allowed.
    Currently, based on the value of EUL_INDEXER_ALLOWED_IPS in settings.py.

    :param request: HttpRequest

    '''
    allowed_ips = settings.EUL_INDEXER_ALLOWED_IPS
    if(allowed_ips != "ANY" and not request.META['REMOTE_ADDR'] in allowed_ips):
        return True

    return False
