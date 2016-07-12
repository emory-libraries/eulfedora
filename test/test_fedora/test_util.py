# file test_fedora/test_api.py
#
#   Copyright 2016 Emory University Libraries
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

from django.views import debug
from unittest import TestCase
import requests

from eulfedora.util import SafeExceptionReporterFilter


class SafeExceptionReportFilterTest(TestCase):

    def test_filter_cleansed(self):
        # sample cleansed stack trace variables as provided by
        # django filter
        cleansed_data = [
            ('reqmeth', requests.get),
            ('url', 'objects/pid:123/datastreams'),
            ('rqst_options', {'params': {u'format': u'xml'},
                              u'auth': ('user', 'pass')})
        ]
        fltr = SafeExceptionReporterFilter()
        cleansed = fltr.filter_cleansed(cleansed_data)
        # password shoud be removed
        # - third set of data variables, second part of the auth tuple
        self.assertNotEqual('pass', cleansed[2][1]['auth'][1])
        self.assertEqual(debug.CLEANSED_SUBSTITUTE,
                         cleansed[2][1]['auth'][1])
        # everything else should be unchanged
        self.assertEqual(cleansed[0], cleansed_data[0])
        self.assertEqual(cleansed[1], cleansed_data[1])
