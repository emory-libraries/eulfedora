# file testcore.py
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

import sys
import unittest

import os
# must be set before importing anything from django
os.environ['DJANGO_SETTINGS_MODULE'] = 'testsettings'

from eulfedora import testutil

def tests_from_modules(modnames):
    return [ unittest.findTestCases(__import__(modname, fromlist=['*']))
             for modname in modnames ]

def get_test_runner():
    if hasattr(testutil, 'FedoraXmlTestRunner'):
        return testutil.FedoraXmlTestRunner()
    else:
        return testutil.FedoraTextTestRunner(sys.stdout, None, 1)


def main(testRunner=None, *args, **kwargs):
    if testRunner is None:
        testRunner = get_test_runner()

    unittest.main(testRunner=testRunner, *args, **kwargs)
