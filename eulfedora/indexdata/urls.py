# file eulfedora/indexdata/urls.py
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

'''
In your projects urls.py, this is to be included in a form similar to:

        urlpatterns = patterns('',
            url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
            #Additional url patterns here,
        )
'''

from django.conf.urls.defaults import *

urlpatterns = patterns('eulfedora.indexdata.views',
    url(r'^$', 'index_config', name='index_config'),
    url(r'^(?P<id>[^/]+)/$', 'index_data', name='index_data'),
)
