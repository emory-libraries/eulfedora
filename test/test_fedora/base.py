# file test_fedora/base.py
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
import unittest
import logging
from eulxml import xmlmap
from eulfedora.api import ApiFacade
from eulfedora.server import Repository
from eulfedora.util import RequestFailed

from localsettings import FEDORA_ROOT, FEDORA_ROOT_NONSSL, \
     FEDORA_USER, FEDORA_PASSWORD, FEDORA_PIDSPACE

logger = logging.getLogger(__name__)

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures')
def fixture_path(fname):
    return os.path.join(FIXTURE_ROOT, fname)

def load_fixture_data(fname):
    with open(fixture_path(fname)) as f:
        return f.read()

class _MinimalFoxml(xmlmap.XmlObject):
    pid = xmlmap.StringField('@PID')

class FedoraTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        self.fedora_fixtures_ingested = []
        self.pidspace = FEDORA_PIDSPACE

        self.repo = Repository(FEDORA_ROOT, FEDORA_USER, FEDORA_PASSWORD)

        # fixture cleanup happens in tearDown, which doesn't always run
        # if a test fails - clean up stale test objects from a previous run here
        stale_objects = list(self.repo.find_objects(pid__contains='%s:*' % self.pidspace))
        if stale_objects:
            print 'Removing %d stale test object(s) in pidspace %s' % (len(stale_objects),
                                                                       self.pidspace)
            for obj in stale_objects:
                try:
                    self.repo.purge_object(obj.pid)
                except RequestFailed as rf:
                    logger.warn('Error purging stale test object %s (TestCase init): %s' % \
                                (obj.pid, rf))
                

    def setUp(self):
        # NOTE: queries require RI flush=True or test objects will not show up in RI
        self.repo.risearch.RISEARCH_FLUSH_ON_QUERY = True
        self.opener = self.repo.opener
        self.api = ApiFacade(self.opener)
        fixtures = getattr(self, 'fixtures', [])
        for fixture in fixtures:
            self.ingestFixture(fixture)

    def tearDown(self):
        for pid in self.fedora_fixtures_ingested:
            try: 
                self.repo.purge_object(pid)
            except RequestFailed as rf:
                logger.warn('Error purging test object %s in tear down: %s' % \
                            (pid, rf))

    def getNextPid(self):
        pidspace = getattr(self, 'pidspace', None)
        return self.repo.get_next_pid(namespace=pidspace)

    def loadFixtureData(self, fname):
        data = load_fixture_data(fname)
        # if pidspace is specified, get a new pid from fedora and set it as the pid in the xml 
        if hasattr(self, 'pidspace'):
            xml = xmlmap.load_xmlobject_from_string(data, _MinimalFoxml)            
            xml.pid = self.getNextPid()
            return xml.serialize()
        else:
            return data

    def ingestFixture(self, fname):
        object = self.loadFixtureData(fname)
        pid = self.repo.ingest(object)
        if pid:
            # we'd like this always to be true. if ingest fails we should
            # throw an exception. that probably hasn't been thoroughly
            # tested yet, though, so we'll check it until it has been.
            self.append_test_pid(pid)

    def append_test_pid(self, pid):
            self.fedora_fixtures_ingested.append(pid)
