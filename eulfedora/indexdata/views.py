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

""":
Generic, re-usable views for use with Fedora-based Django projects. These views
expose data via a webservice to eulindexer (if running). These views currently
return data in JSON form. 

Projects that use this module should include the following settings in their
``settings.py``::

    # Index server url. In this example case, we are wish to push data to a Solr instance.
    INDEX_SERVER_URL = "http://localhost:8983/solr/"
    # IPs that will be allowed to access this webservice.
    INDEXER_ALLOWED_IPS = "ANY" #Or put in a list such as ("127.0.0.1", "127.0.0.2")

Using these views (in the simpler cases) should be as easy as the following:

    In urls.py of your application:
        
        from django.conf.urls.defaults import *
    
        urlpatterns = patterns('',
            url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
            # Additional url patterns here,
        )

    In settings.py of your application:

        INSTALLED_APPS = (
            'eulfedora.indexdata'
            # Additional installed applications here,
        )

"""

import logging
import os
import json
from django.utils import simplejson
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseForbidden, \
    HttpResponseBadRequest
from eulfedora.models import DigitalObject


logger = logging.getLogger(__name__)

def index_details(request):
    '''View to return the CMODELS and INDEXES this project uses. This is the default (no parameter)
    view of this application.

    :param request: HttpRequest

    '''
    #Ensure permission to this resource is allowed. Currently based on IP only.
    if _permission_denied_check(request):
        return HttpResponseForbidden('Access to this web service was denied.', content_type='text/html')

    #Create the content models list.
    content_models = []
    for cls in DigitalObject.defined_types.itervalues():
        if hasattr(cls, 'index') and hasattr(cls, 'CONTENT_MODELS') and len(cls.CONTENT_MODELS) == 1:
            content_models.append({'CONTENT_MODEL': str(cls.CONTENT_MODELS[0])})
    
    #Get the indexer url specified in the settings.
    indexer_url = settings.INDEX_SERVER_URL

    #Create a combined result of the content models and the indexer url.
    combined_response = []
    combined_response.append({'CONTENT_MODELS': content_models, 'INDEXER_URL': indexer_url})
    json_response = simplejson.dumps(combined_response)
    
    return HttpResponse(json_response, content_type='application/javascript')

def index_data(request, id):
    return HttpResponse('Implement me', content_type='text/html')

def _permission_denied_check(request):
    '''Internal function to verify that access to this webservice is allowed.
    Currently, based on the value of INDEXER_ALLOWED_IPS in settings.py.

    :param request: HttpRequest

    '''
    allowed_ips = settings.INDEXER_ALLOWED_IPS
    if(allowed_ips != "ANY" and not request.META['REMOTE_ADDR'] in allowed_ips):
        return True

    return False
