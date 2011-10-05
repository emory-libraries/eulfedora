# file eulfedora/testutil.py
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
:mod:`eulfedora.testutil` provides custom Django test suite runners with
Fedora environment setup / teardown for all tests.

To use, configure as test runner in your Django settings::

   TEST_RUNNER = 'eulfedora.testutil.FedoraTextTestSuiteRunner'

When :mod:`xmlrunner` is available, xmlrunner variants are also available.
To use this test runner, configure your Django test runner as follows::

    TEST_RUNNER = 'eulfedora.testutil.FedoraXmlTestSuiteRunner'

The xml variant honors the same django settings that the xmlrunner
django testrunner does (TEST_OUTPUT_DIR, TEST_OUTPUT_VERBOSE, and
TEST_OUTPUT_DESCRIPTIONS).

Any :class:`~eulfedora.server.Repository` instances created after the
test suite starts will automatically connect to the test collection.
If you have a test pidspace configured, that will be used for the
default pidspace when creating test objects; if you have a pidspace
but not a test pidspace, the set to use a pidspace of
'yourpidspace-test' for the duration of the tests.  Any objects in the
test pidspace will be removed from the Fedora instance after the tests
finish.

.. note::

   The test configurations are not switched until after your test code
   is loaded, so any repository connections should **not** be made at
   class instantiation time, but in a setup method.

----

"""

import logging

import unittest2 as unittest
from django.conf import settings
from django.core.management import call_command
from django.test.simple import DjangoTestSuiteRunner

from eulfedora.server import Repository, init_pooled_connection
from eulfedora.util import RequestFailed

logger = logging.getLogger(__name__)

class FedoraTestWrapper(object):
    '''A `context manager <http://docs.python.org/library/stdtypes.html#context-manager-types>`_
    that replaces the Django fedora configuration with a test configuration
    inside the block, replacing the original configuration when the block
    exits. All objects are purged from the defined test pidspace before and
    after running tests.
    '''

    def __init__(self):
        self.stored_default_fedora_root = None
        self.stored_default_fedora_pidspace = None
        
    def __enter__(self):
        self.use_test_fedora()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore_fedora_root()

    def use_test_fedora(self):
        self.stored_default_fedora_root = getattr(settings, "FEDORA_ROOT", None)
        self.stored_default_fedora_pidspace = getattr(settings, "FEDORA_PIDSPACE", None)

        if getattr(settings, "FEDORA_TEST_ROOT", None):
            settings.FEDORA_ROOT = settings.FEDORA_TEST_ROOT
            print "Switching to test Fedora: %s" % settings.FEDORA_ROOT
            # pooled fedora connection gets initialized before this change;
            # re-initialize connection with new fedora root configured
            init_pooled_connection()
        else:
            print "FEDORA_TEST_ROOT is not configured in settings; tests will run against %s" % \
                settings.FEDORA_ROOT

        if getattr(settings, "FEDORA_TEST_PIDSPACE", None):
            settings.FEDORA_PIDSPACE = settings.FEDORA_TEST_PIDSPACE
        elif getattr(settings, "FEDORA_PIDSPACE", None):
            settings.FEDORA_PIDSPACE = "%s-test" % settings.FEDORA_PIDSPACE
        print "Using Fedora pidspace: %s" % settings.FEDORA_PIDSPACE

        # remove any test objects left over from a previous test run
        self.remove_test_objects()
        # run syncrepo to load any content models or fixtures
        # - pass any test fedora credentials to syncrepo
        test_user = getattr(settings, 'FEDORA_TEST_USER', None)
        test_pwd = getattr(settings, 'FEDORA_TEST_PASSWORD', None)
        call_command('syncrepo', username=test_user, password=test_pwd)

    def restore_fedora_root(self):
        # if there was a pidspace configured, clean up any test objects
        msgs = []
        if self.stored_default_fedora_pidspace is not None:
            self.remove_test_objects()
            msgs.append("Restoring Fedora pidspace: %s" % self.stored_default_fedora_pidspace)
            settings.FEDORA_PIDSPACE = self.stored_default_fedora_pidspace        
        if self.stored_default_fedora_root is not None:
            msgs.append("Restoring Fedora root: %s" % self.stored_default_fedora_root)
            settings.FEDORA_ROOT = self.stored_default_fedora_root
            # re-initialize pooled connection with restored fedora root
            init_pooled_connection()
        if msgs:
            print '\n', '\n'.join(msgs)

    def remove_test_objects(self):
        # remove any leftover test object before or after running tests
        # NOTE: This method expects to be called only when FEDORA_PIDSPACE has been
        # switched to a test pidspace

        # use test fedora credentials if they are set
        repo = Repository(root=getattr(settings, 'FEDORA_TEST_ROOT', None),
                          username=getattr(settings, 'FEDORA_TEST_USER', None),
                          password=getattr(settings, 'FEDORA_TEST_PASSWORD', None))
        test_objects = repo.find_objects(pid__contains='%s:*' % settings.FEDORA_PIDSPACE)
        count = 0
        for obj in test_objects:
            # if objects are unexpectedly not being cleaned up, pid/label may help
            # to isolate which test is creating the leftover objects
            try:
                repo.purge_object(obj.pid, "removing test object")
                # NOTE: not displaying label because we may not have permission to access it
                logger.info('Purged test object %s' % obj.pid)
                count += 1
            except RequestFailed:
                logger.warn('Error purging test object %s' % obj.pid)
        if count:
            print "Removed %s test object(s) with pidspace %s" % (count, settings.FEDORA_PIDSPACE)

    @classmethod
    def wrap_test(cls, test):
        def wrapped_test(result):
            with cls():
                return test(result)
        return wrapped_test

alternate_test_fedora = FedoraTestWrapper


class FedoraTextTestRunner(unittest.TextTestRunner):
    '''A :class:`unittest.TextTestRunner` that wraps test execution in a
    :class:`FedoraTestWrapper`.
    '''
    def run(self, test):
        wrapped_test = alternate_test_fedora.wrap_test(test)
        return super(FedoraTextTestRunner, self).run(wrapped_test)

class FedoraTextTestSuiteRunner(DjangoTestSuiteRunner):
    '''Extend :class:`django.test.simple.DjangoTestSuiteRunner` to setup and
    teardown the Fedora test environment.'''
    def run_suite(self, suite, **kwargs):
        return FedoraTextTestRunner(verbosity=self.verbosity,
                                    failfast=self.failfast).run(suite)

try:
    # when xmlrunner is available, define xmltest variants

    import xmlrunner

    class FedoraXmlTestRunner(xmlrunner.XMLTestRunner):
        '''A :class:`xmlrunner.XMLTestRunner` that wraps test execution in a
        :class:`FedoraTestWrapper`.
        '''
        def __init__(self):
            # pick up settings as expected by django xml test runner
            verbose = getattr(settings, 'TEST_OUTPUT_VERBOSE', False)
            descriptions = getattr(settings, 'TEST_OUTPUT_DESCRIPTIONS', False)
            output = getattr(settings, 'TEST_OUTPUT_DIR', 'test-results')

            super_init = super(FedoraXmlTestRunner, self).__init__
            super_init(verbose=verbose, descriptions=descriptions, output=output)

        def run(self, test):
            wrapped_test = alternate_test_fedora.wrap_test(test)
            return super(FedoraXmlTestRunner, self).run(wrapped_test)
    
    class FedoraXmlTestSuiteRunner(FedoraTextTestSuiteRunner):
        '''Extend :class:`django.test.simple.DjangoTestSuiteRunner` to setup
        and teardown the Fedora test environment and export test results in
        XML.'''
        def run_suite(self, suite, **kwargs):
            return FedoraXmlTestRunner().run(suite)


except ImportError:
    # xmlrunner not available. simply don't define those classes
    pass
