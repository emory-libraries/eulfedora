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
:mod:`eulfedora.testutil` provides custom test suite runners with
Fedora environment setup / teardown for all tests.

To use, configure as test runner in your Django settings::

   TEST_RUNNER = 'eulfedora.testutil.FedoraTestSuiteRunner'

When :mod:`xmlrunner` is available, xmlrunner variants are also
available.  To use this test runner, configure your test runner as
follows::

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

logger = logging.getLogger(__name__)


class FedoraTestResult(unittest.TextTestResult):
    '''Extend :class:`unittest2.TextTestResult` to take advantage of
    :meth:`startTestRun` and :meth:`stopTestRun` to do environmental
    test setup and teardown before and after all tests run.
    '''
    _stored_default_fedora_root = None
    _stored_default_fedora_pidspace = None

    def startTestRun(self):
        '''Switch Django settings for FEDORA access to test
        configuration, and load any repository fixtures (such as
        content models or initial objects).'''
        super(FedoraTestResult, self).startTestRun()
        self._use_test_fedora()

    def stopTestRun(self):
        '''Switch Django settings for FEDORA access out of test
        configuration and back into normal settings, and remove any
        leftover objects in with the test pidspace and in the test
        repository.'''
        self._restore_fedora_root()
        super(FedoraTestResult, self).stopTestRun()

    def _use_test_fedora(self):
        self._stored_default_fedora_root = getattr(settings, "FEDORA_ROOT", None)
        self._stored_default_fedora_pidspace = getattr(settings, "FEDORA_PIDSPACE", None)

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

    def _restore_fedora_root(self):
        # if there was a pidspace configured, clean up any test objects
        msgs = []
        if self._stored_default_fedora_pidspace is not None:
            self.remove_test_objects()
            msgs.append("Restoring Fedora pidspace: %s" % self._stored_default_fedora_pidspace)
            settings.FEDORA_PIDSPACE = self._stored_default_fedora_pidspace        
        if self._stored_default_fedora_root is not None:
            msgs.append("Restoring Fedora root: %s" % self._stored_default_fedora_root)
            settings.FEDORA_ROOT = self._stored_default_fedora_root
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
            logger.info('Purging test object %s - %s' % (obj.pid, obj.label))
            repo.purge_object(obj.pid, "removing test object")
            count += 1
        if count:
            print "Removed %s test object(s) with pidspace %s" % (count, settings.FEDORA_PIDSPACE)


class FedoraTestSuiteRunner(DjangoTestSuiteRunner):
    '''Extend :class:`django.test.simple.DjangoTestSuiteRunner` to use
    :class:`FedoraTestResult` as the result class.'''
    
    def run_suite(self, suite, **kwargs):
        # call the exact same way that django does, with the addition of our resultclass
        return unittest.TextTestRunner(resultclass=FedoraTestResult,
                                       verbosity=self.verbosity, failfast=self.failfast).run(suite)

try:
    # when xmlrunner is available, define xmltest variants

    import xmlrunner
    
    class FedoraXmlTestResult(xmlrunner._XMLTestResult, FedoraTestResult):
        # xml test result logic with our custom startTestRun/stopTestRun
        def __init__(self, **kwargs):
            # sort out kwargs for the respective init methods;
            # need to call both so everything is set up properly
            testrunner_args = dict((key, val) for key, val in kwargs.iteritems()
                                   if key in ['stream', 'descriptions', 'verbosity'])
            FedoraTestResult.__init__(self, **testrunner_args)

            xmlargs = dict((key, val) for key, val in kwargs.iteritems() if
                           key in ['stream', 'descriptions', 'verbosity', 'elapsed_times'])
            xmlrunner._XMLTestResult.__init__(self, **xmlargs)
            
    class FedoraXmlTestRunner(xmlrunner.XMLTestRunner):
        # XMLTestRunner doesn't currently take a resultclass init option;
        # extend make_result to override test result class that will be used
        def _make_result(self):
            """Create the TestResult object which will be used to store
            information about the executed tests.
            """
            return FedoraXmlTestResult(stream=self.stream, descriptions=self.descriptions, \
                                       verbosity=self.verbosity, elapsed_times=self.elapsed_times)
    
    class FedoraXmlTestSuiteRunner(DjangoTestSuiteRunner):
        '''Extend :class:`django.test.simple.DjangoTestSuiteRunner` to use
        :class:`FedoraTestResult` as the result class.'''
        # combination of DjangoTestSuiteRunner with xmlrunner django test runner variant
        
        def run_suite(self, suite, **kwargs):
            # pick up settings as expected by django xml test runner
            settings.DEBUG = False
            verbose = getattr(settings, 'TEST_OUTPUT_VERBOSE', False)
            descriptions = getattr(settings, 'TEST_OUTPUT_DESCRIPTIONS', False)
            output = getattr(settings, 'TEST_OUTPUT_DIR', '.')

            # call roughly the way that xmlrunner does, with our customized test runner
            return FedoraXmlTestRunner(verbose=verbose, descriptions=descriptions,
                                       output=output).run(suite)

except ImportError:
    pass
