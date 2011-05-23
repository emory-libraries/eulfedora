# file testsettings.py
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

import os

# test secret key for eulfedora.cryptutil tests
SECRET_KEY = 'abcdefghijklmnopqrstuvwxyz1234567890'


INSTALLED_APPS = (
    'eulfedora',
)


FEDORA_FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'test_fedora', 'fixtures')

from localsettings import *
