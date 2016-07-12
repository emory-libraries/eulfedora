# file test_fedora/test_api.py
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

from datetime import datetime, timedelta
from dateutil.tz import tzutc
import hashlib
from lxml import etree
from mock import patch
from rdflib import URIRef
import re
import requests
from time import sleep
import tempfile
import warnings

from test.test_fedora.base import FedoraTestCase, load_fixture_data
from test.testsettings import FEDORA_ROOT_NONSSL,\
    FEDORA_USER, FEDORA_PASSWORD, FEDORA_PIDSPACE
from eulfedora.api import REST_API, API_A_LITE, UnrecognizedQueryLanguage
from eulfedora.models import DigitalObject
from eulfedora.rdfns import model as modelns
from eulfedora.util import fedoratime_to_datetime, md5sum, \
     datetime_to_fedoratime, RequestFailed, ChecksumMismatch, parse_rdf, \
     force_bytes, force_text
from eulfedora.xml import FEDORA_MANAGE_NS, FEDORA_ACCESS_NS


# TODO: test for errors - bad pid, dsid, etc

ONE_SEC = timedelta(seconds=1)


class TestREST_API(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    TEXT_CONTENT = """This is my text content for a new datastream.

Hey, nonny-nonny."""

    def _add_text_datastream(self):
        # add a text datastream to the current test object - used by multiple tests
        FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
        FILE.write(self.TEXT_CONTENT)
        FILE.flush()

        # info for calling addDatastream, and return
        ds = {'id': 'TEXT', 'label': 'text datastream', 'mimeType': 'text/plain',
            'controlGroup': 'M', 'logMessage': "creating new datastream",
            'checksumType': 'MD5'}

        # return (r.status_code == requests.codes.created, r.content)
        with open(FILE.name) as data:
            r = self.rest_api.addDatastream(self.pid, ds['id'], ds['label'],
                ds['mimeType'], ds['logMessage'], ds['controlGroup'], content=data,
                checksumType=ds['checksumType'])

        FILE.close()
        return ((r.status_code == requests.codes.created, r.content), ds)

    def setUp(self):
        super(TestREST_API, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.rest_api = REST_API(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)
        self.today = datetime.utcnow().date()

    # API-A calls

    def test_findObjects(self):
        # search for current test object  (restrict to current pidspace to avoid bogus failures)
        r = self.rest_api.findObjects("ownerId~tester pid~%s:*" % FEDORA_PIDSPACE)
        found = r.text
        self.assert_('<result ' in found)
        self.assert_('<resultList>' in found)
        self.assert_('<pid>%s</pid>' % self.pid in found)

        # crazy search that shouldn't match anything
        r = self.rest_api.findObjects("title~supercalifragilistexpi...")
        self.assert_('<objectFields>' not in r.text)

        # search for everything - get enough results to get a session token
        # - note that current test fedora includes a number of control objects
        # - using smaller chunk size to ensure pagination
        r = self.rest_api.findObjects("title~*", chunksize=2)
        self.assert_('<listSession>' in r.text)
        self.assert_('<token>' in r.text)

        # search by terms
        r = self.rest_api.findObjects(terms="more dat? in it than a *")
        self.assert_('<pid>%s</pid>' % self.pid in r.text)

        # NOTE: not testing resumeFind here because it would require parsing the xml
        # for the session token - tested at the server/Repository level

    def test_getDatastreamDissemination(self):
        r = self.rest_api.getDatastreamDissemination(self.pid, "DC")
        dc = r.text
        self.assert_("<dc:title>A partially-prepared test object</dc:title>" in dc)
        self.assert_("<dc:description>This object has more data" in dc)
        self.assert_("<dc:identifier>%s</dc:identifier>" % self.pid in dc)

        # get server datetime param (the hard way) for testing
        r = self.rest_api.getDatastream(self.pid, "DC")
        dsprofile_node = etree.fromstring(r.content, base_url=r.url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)', namespaces={'m': FEDORA_MANAGE_NS})
        created = fedoratime_to_datetime(created_s)

        # with date-time param
        r = self.rest_api.getDatastreamDissemination(self.pid, "DC",
            asOfDateTime=created + ONE_SEC)
        postcreate_dc = r.text
        self.assertEqual(dc, postcreate_dc)    # unchanged within its first sec

        # bogus datastream
        self.assertRaises(Exception, self.rest_api.getDatastreamDissemination,
            self.pid, "BOGUS")

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getDatastreamDissemination,
            "bogus:pid", "BOGUS")

        # return_http_response
        response = self.rest_api.getDatastreamDissemination(self.pid, 'DC')
        self.assert_(isinstance(response, requests.Response),
                     'getDatastreamDissemination should return a response object')
        # datastream content should still be accessible
        self.assertEqual(dc, response.text)

    # NOTE: getDissemination not available in REST API until Fedora 3.3
    def test_getDissemination(self):
        # testing with built-in fedora dissemination
        r = self.rest_api.getDissemination(self.pid, "fedora-system:3", "viewItemIndex")
        self.assert_('<title>Object Items HTML Presentation</title>' in r.text)
        self.assert_(self.pid in r.text)

        # return_http_response
        response = self.rest_api.getDissemination(self.pid, "fedora-system:3", "viewItemIndex")
        self.assert_(isinstance(response, requests.Response),
                     'getDissemination should return a response object')
        # datastream content should still be accessible
        self.assert_(self.pid in force_text(response.content))

    def test_getObjectHistory(self):
        r = self.rest_api.getObjectHistory(self.pid)
        self.assert_('<fedoraObjectHistory' in r.text)
        self.assert_('pid="%s"' % self.pid in r.text)
        self.assert_('<objectChangeDate>%s' % self.today in r.text)

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getObjectHistory, "bogus:pid")

    def test_getObjectProfile(self):
        r = self.rest_api.getObjectProfile(self.pid)
        profile = r.text
        self.assert_('<objectProfile' in profile)
        self.assert_('pid="%s"' % self.pid in profile)
        self.assert_('<objLabel>A partially-prepared test object</objLabel>' in profile)
        self.assert_('<objOwnerId>tester</objOwnerId>' in profile)
        self.assert_('<objCreateDate>%s' % self.today in profile)
        self.assert_('<objLastModDate>%s' % self.today in profile)
        self.assert_('<objState>A</objState>' in profile)
        # unchecked: objDissIndexViewURL, objItemIndexViewURL

        # get server datetime param (the hard way) for testing
        profile_node = etree.fromstring(r.content, base_url=r.url)
        created_s = profile_node.xpath('string(a:objCreateDate)', namespaces={'a': FEDORA_ACCESS_NS})
        created = fedoratime_to_datetime(created_s)

        # with time
        r = self.rest_api.getObjectProfile(self.pid,
                        asOfDateTime=created + ONE_SEC)
        profile_now = r.text
        # NOTE: profile content is not exactly the same because it includes a datetime attribute
        self.assert_('pid="%s"' % self.pid in profile_now)
        self.assert_('<objLabel>A partially-prepared test object</objLabel>' in profile_now)

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getObjectHistory, "bogus:pid")

    def test_listDatastreams(self):
        r = self.rest_api.listDatastreams(self.pid)
        self.assert_('<objectDatastreams' in r.text)
        self.assert_('<datastream dsid="DC" label="Dublin Core" mimeType="text/xml"' in r.text)

        # bogus pid
        self.assertRaises(Exception, self.rest_api.listDatastreams, "bogus:pid")

    def test_listMethods(self):
        r = self.rest_api.listMethods(self.pid)
        methods = r.text
        self.assert_('<objectMethods' in methods)
        self.assert_('pid="%s"' % self.pid in methods)
        # default fedora methods, should be available on every object
        self.assert_('<sDef pid="fedora-system:3" ' in methods)
        self.assert_('<method name="viewObjectProfile"' in methods)
        self.assert_('<method name="viewItemIndex"' in methods)

        # methods for a specified sdef
        # NOTE: this causes a 404 error; fedora bug? possibly does not work with system methods?
        # methods = self.rest_api.listMethods(self.pid, 'fedora-system:3')

        self.assertRaises(Exception, self.rest_api.listMethods, "bogus:pid")

    # API-M calls

    def test_addDatastream(self):
        # returns result from addDatastream call and info used for add
        ((added, msg), ds) = self._add_text_datastream()

        self.assertTrue(added)  # response from addDatastream
        r = self.rest_api.getObjectXML(self.pid)
        message = r.content
        self.assert_(ds['logMessage'] in force_text(message))
        r = self.rest_api.listDatastreams(self.pid)
        self.assert_('<datastream dsid="%(id)s" label="%(label)s" mimeType="%(mimeType)s" />'
            % ds in r.text)
        r = self.rest_api.getDatastream(self.pid, ds['id'])
        ds_profile = r.text
        self.assert_('dsID="%s"' % ds['id'] in ds_profile)
        self.assert_('<dsLabel>%s</dsLabel>' % ds['label'] in ds_profile)
        self.assert_('<dsVersionID>%s.0</dsVersionID>' % ds['id'] in ds_profile)
        self.assert_('<dsCreateDate>%s' % self.today in ds_profile)
        self.assert_('<dsState>A</dsState>' in ds_profile)
        self.assert_('<dsMIME>%s</dsMIME>' % ds['mimeType'] in ds_profile)
        self.assert_('<dsControlGroup>%s</dsControlGroup>' % ds['controlGroup'] in ds_profile)
        self.assert_('<dsVersionable>true</dsVersionable>' in ds_profile)

        # content returned from fedora should be exactly what we started with
        r = self.rest_api.getDatastreamDissemination(self.pid, ds['id'])
        self.assertEqual(self.TEXT_CONTENT, r.text)

        # invalid checksum
        self.assertRaises(ChecksumMismatch, self.rest_api.addDatastream, self.pid,
            "TEXT2", "text datastream",  mimeType="text/plain", logMessage="creating TEXT2",
            content='<some> text content</some>', checksum='totally-bogus-not-even-an-MD5',
            checksumType='MD5')

        # invalid checksum without a checksum type - warning, but no checksum mismatch
        with warnings.catch_warnings(record=True) as w:
            self.rest_api.addDatastream(self.pid,
                "TEXT2", "text datastream",  mimeType="text/plain", logMessage="creating TEXT2",
                content='<some> text content</some>', checksum='totally-bogus-not-even-an-MD5',
                checksumType=None)
            self.assertEqual(1, len(w),
                'calling addDatastream with checksum but no checksum type should generate a warning')
            self.assert_('Fedora will ignore the checksum' in str(w[0].message))

        # attempt to add to a non-existent object
        FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
        FILE.write("bogus")
        FILE.flush()

        with open(FILE.name) as textfile:
            self.assertRaises(RequestFailed, self.rest_api.addDatastream, 'bogus:pid',
              'TEXT', 'text datastream',
              mimeType='text/plain', logMessage='creating new datastream',
              controlGroup='M', content=textfile)

        FILE.close()

    # relationship predicates for testing
    rel_isMemberOf = "info:fedora/fedora-system:def/relations-external#isMemberOf"
    rel_owner = "info:fedora/fedora-system:def/relations-external#owner"

    def test_addRelationship(self):
        # rel to resource
        added = self.rest_api.addRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                              force_text(modelns.hasModel),
                                              'info:fedora/pid:123', False)
        self.assertTrue(added)
        r = self.rest_api.getDatastreamDissemination(self.pid, 'RELS-EXT')
        self.assert_('<hasModel' in r.text)
        self.assert_('rdf:resource="info:fedora/pid:123"' in r.text)

        # literal
        added = self.rest_api.addRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                              self.rel_owner, "johndoe", True)
        self.assertTrue(added)
        r = self.rest_api.getDatastreamDissemination(self.pid, 'RELS-EXT')
        self.assert_('<owner' in r.text)
        self.assert_('>johndoe<' in r.text)

        # bogus pid
        self.assertRaises(RequestFailed, self.rest_api.addRelationship,
            'bogus:pid', 'info:fedora/bogus:pid', self.rel_owner, 'johndoe', True)

    def test_getRelationships(self):
        # add relations to retrieve
        self.rest_api.addRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                   force_text(modelns.hasModel), "info:fedora/pid:123", False)
        self.rest_api.addRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                   self.rel_owner, "johndoe", True)

        r = self.rest_api.getRelationships(self.pid)
        graph = parse_rdf(r.content, r.url)

        # check total number: fedora-system cmodel + two just added
        self.assertEqual(3, len(list(graph)))
        # newly added triples should be included in the graph
        self.assert_((URIRef('info:fedora/%s' % self.pid),
                      modelns.hasModel,
                      URIRef('info:fedora/pid:123')) in graph)

        self.assertEqual('johndoe', str(graph.value(subject=URIRef('info:fedora/%s' % self.pid),
                                                predicate=URIRef(self.rel_owner))))

        # get rels for a single predicate
        r = self.rest_api.getRelationships(self.pid, predicate=self.rel_owner)
        graph = parse_rdf(r.content, r.url)
        # should include just the one we asked for
        self.assertEqual(1, len(list(graph)))

        self.assertEqual('johndoe', str(graph.value(subject=URIRef('info:fedora/%s' % self.pid),
                                                predicate=URIRef(self.rel_owner))))

    def test_compareDatastreamChecksum(self):
        # create datastream with checksum
        (added, ds) = self._add_text_datastream()
        r = self.rest_api.compareDatastreamChecksum(self.pid, ds['id'])

        mdsum = hashlib.md5()
        mdsum.update(force_bytes(self.TEXT_CONTENT))
        text_md5 = mdsum.hexdigest()
        self.assert_('<dsChecksum>%s</dsChecksum>' % text_md5 in r.text)
        # FIXME: how to test that checksum has actually been checked?

        # check for log message in audit trail
        r = self.rest_api.getObjectXML(self.pid)
        self.assert_(ds['logMessage'] in r.text)

    def test_export(self):
        r = self.rest_api.export(self.pid)
        export = r.text
        self.assert_('<foxml:datastream' in export)
        self.assert_('PID="%s"' % self.pid in export)
        self.assert_('<foxml:property' in export)
        self.assert_('<foxml:datastream ID="DC" ' in export)

        # default 'context' is public; also test migrate & archive
        # FIXME/TODO: add more datastreams/versions so export formats differ ?

        r = self.rest_api.export(self.pid, context="migrate")
        self.assert_('<foxml:datastream' in r.text)

        r = self.rest_api.export(self.pid, context="archive")
        self.assert_('<foxml:datastream' in r.text)

        # bogus id
        self.assertRaises(Exception, self.rest_api.export, "bogus:pid")

    def test_getDatastream(self):
        r = self.rest_api.getDatastream(self.pid, "DC")
        ds_profile = r.content
        ds_profile_text = r.text
        self.assert_('<datastreamProfile' in ds_profile_text)
        self.assert_('pid="%s"' % self.pid in ds_profile_text)
        self.assert_('dsID="DC"' in ds_profile_text)
        self.assert_('<dsLabel>Dublin Core</dsLabel>' in ds_profile_text)
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in ds_profile_text)
        self.assert_('<dsCreateDate>%s' % self.today in ds_profile_text)
        self.assert_('<dsState>A</dsState>' in ds_profile_text)
        self.assert_('<dsMIME>text/xml</dsMIME>' in ds_profile_text)
        self.assert_('<dsControlGroup>X</dsControlGroup>' in ds_profile_text)
        self.assert_('<dsVersionable>true</dsVersionable>' in ds_profile_text)

        # get server datetime param (the hard way) for testing
        dsprofile_node = etree.fromstring(ds_profile, base_url=r.url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)', namespaces={'m': FEDORA_MANAGE_NS})
        created = fedoratime_to_datetime(created_s)

        # with date param
        r = self.rest_api.getDatastream(self.pid, "DC",
                        asOfDateTime=created + ONE_SEC)
        ds_profile_now = r.text
        # NOTE: contents are not exactly equal because 'now' version includes a dateTime attribute
        self.assert_('<dsLabel>Dublin Core</dsLabel>' in ds_profile_now)
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in ds_profile_now)

        # bogus datastream id on valid pid
        self.assertRaises(Exception, self.rest_api.getDatastream, self.pid, "BOGUS")

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getDatastream, "bogus:pid", "DC")

    def test_getDatastreamHistory(self):
        r = self.rest_api.getDatastreamHistory(self.pid, "DC")
        # default format is html
        self.assert_('<h3>Datastream History View</h3>' in r.text)
        r = self.rest_api.getDatastreamHistory(self.pid, "DC", format='xml')
        data = r.text
        # check various pieces of datastream info
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in data)
        self.assert_('<dsControlGroup>X</dsControlGroup>' in data)
        self.assert_('<dsLabel>Dublin Core</dsLabel>' in data)
        self.assert_('<dsVersionable>true</dsVersionable>' in data)
        self.assert_('<dsMIME>text/xml</dsMIME>' in data)
        self.assert_('<dsState>A</dsState>' in data)

        # modify DC so there are multiple versions
        new_dc = """<oai_dc:dc
            xmlns:dc='http://purl.org/dc/elements/1.1/'
            xmlns:oai_dc='http://www.openarchives.org/OAI/2.0/oai_dc/'>
          <dc:title>Test-Object</dc:title>
          <dc:description>modified!</dc:description>
        </oai_dc:dc>"""
        self.rest_api.modifyDatastream(self.pid, "DC", "DCv2Dublin Core",
            mimeType="text/xml", logMessage="updating DC", content=new_dc)
        r = self.rest_api.getDatastreamHistory(self.pid, 'DC', format='xml')
        data = r.text
        # should include both versions
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in data)
        self.assert_('<dsVersionID>DC.1</dsVersionID>' in data)

        # bogus datastream
        self.assertRaises(RequestFailed, self.rest_api.getDatastreamHistory,
                          self.pid, "BOGUS")
        # bogus pid
        self.assertRaises(RequestFailed, self.rest_api.getDatastreamHistory,
                          "bogus:pid", "DC")

    def test_getNextPID(self):
        r = self.rest_api.getNextPID()
        self.assert_('<pidList' in r.text)
        self.assert_('<pid>' in r.text)

        r = self.rest_api.getNextPID(numPIDs=3, namespace="test-ns")
        self.assertEqual(3, r.text.count("<pid>test-ns:"))

    def test_getObjectXML(self):
        # update the object so we can look for audit trail in object xml
        added, ds = self._add_text_datastream()
        r = self.rest_api.getObjectXML(self.pid)
        objxml = r.text
        self.assert_('<foxml:digitalObject' in objxml)
        self.assert_('<foxml:datastream ID="DC" ' in objxml)
        # audit trail accessible in full xml
        self.assert_('<audit:auditTrail ' in objxml)

        # bogus id
        self.assertRaises(Exception, self.rest_api.getObjectXML, "bogus:pid")

    def test_ingest(self):
        obj = self.loadFixtureData('basic-object.foxml')
        r = self.rest_api.ingest(obj)
        pid = r.content
        self.assertTrue(pid)
        self.rest_api.purgeObject(force_text(pid))

        # test ingesting with log message
        r = self.rest_api.ingest(obj, "this is my test ingest message")
        pid = r.text
        # ingest message is stored in AUDIT datastream
        # - can currently only be accessed by retrieving entire object xml
        r = self.rest_api.getObjectXML(pid)
        self.assertTrue("this is my test ingest message" in r.text)
        self.rest_api.purgeObject(pid, "removing test ingest object")

    def test_modifyDatastream(self):
        # add a datastream to be modified
        added, ds = self._add_text_datastream()

        new_text = """Sigh no more, ladies sigh no more.
Men were deceivers ever.
So be you blythe and bonny, singing hey-nonny-nonny."""
        FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
        FILE.write(new_text)
        FILE.flush()

        # modify managed datastream by file
        r = self.rest_api.modifyDatastream(self.pid, ds['id'], "text datastream (modified)",
            mimeType="text/other", logMessage="modifying TEXT datastream", content=open(FILE.name))
        self.assertTrue(r.status_code == requests.codes.ok)
        # log message in audit trail
        r = self.rest_api.getObjectXML(self.pid)
        self.assert_('modifying TEXT datastream' in r.text)

        r = self.rest_api.getDatastream(self.pid, ds['id'])
        ds_profile = r.text
        self.assert_('<dsLabel>text datastream (modified)</dsLabel>' in ds_profile)
        self.assert_('<dsVersionID>%s.1</dsVersionID>' % ds['id'] in ds_profile)
        self.assert_('<dsState>A</dsState>' in ds_profile)
        self.assert_('<dsMIME>text/other</dsMIME>' in ds_profile)

        r = self.rest_api.getDatastreamDissemination(self.pid, ds['id'])
        self.assertEqual(r.text, new_text)

        # modify DC (inline xml) by string
        new_dc = """<oai_dc:dc
            xmlns:dc='http://purl.org/dc/elements/1.1/'
            xmlns:oai_dc='http://www.openarchives.org/OAI/2.0/oai_dc/'>
          <dc:title>Test-Object</dc:title>
          <dc:description>modified!</dc:description>
        </oai_dc:dc>"""
        r = self.rest_api.modifyDatastream(self.pid, "DC", "Dublin Core",
            mimeType="text/xml", logMessage="updating DC", content=new_dc)
        self.assertTrue(r.status_code == requests.codes.ok)
        r = self.rest_api.getDatastreamDissemination(self.pid, "DC")
        # fedora changes whitespace in xml, so exact test fails
        dc = r.text
        self.assert_('<dc:title>Test-Object</dc:title>' in dc)
        self.assert_('<dc:description>modified!</dc:description>' in dc)

        # invalid checksum
        self.assertRaises(ChecksumMismatch, self.rest_api.modifyDatastream, self.pid,
            "DC", "Dublin Core",  mimeType="text/xml", logMessage="updating DC",
            content=new_dc, checksum='totally-bogus-not-even-an-MD5', checksumType='MD5')

        # bogus datastream on valid pid
        self.assertRaises(RequestFailed, self.rest_api.modifyDatastream, self.pid,
            "BOGUS", "Text DS",  mimeType="text/plain", logMessage="modifiying non-existent DS",
             content=open(FILE.name))

        # bogus pid
        self.assertRaises(RequestFailed, self.rest_api.modifyDatastream, "bogus:pid",
             "TEXT", "Text DS", mimeType="text/plain", logMessage="modifiying non-existent DS",
              content=open(FILE.name))
        FILE.close()

    def test_modifyObject(self):
        r = self.rest_api.modifyObject(self.pid, "modified test object", "testuser",
            "I", "testing modify object")
        modified = (r.status_code == requests.codes.ok)
        self.assertTrue(modified)
        # log message in audit trail
        r = self.rest_api.getObjectXML(self.pid)
        self.assert_('testing modify object' in r.text)

        r = self.rest_api.getObjectProfile(self.pid)
        profile = r.text
        self.assert_('<objLabel>modified test object</objLabel>' in profile)
        self.assert_('<objOwnerId>testuser</objOwnerId>' in profile)
        self.assert_('<objState>I</objState>' in profile)

        # bogus id
        self.assertRaises(RequestFailed, self.rest_api.modifyObject, "bogus:pid",
            "modified test object", "testuser",  "I", "testing modify object")

    def test_purgeDatastream(self):
        # add a datastream that can be purged
        (added, dsprofile), ds = self._add_text_datastream()
        # grab datastream creation date from addDatastream result to test purge result
        dsprofile_node = etree.fromstring(dsprofile)
        created = dsprofile_node.xpath('string(m:dsCreateDate)', namespaces={'m': FEDORA_MANAGE_NS})

        # purgeDatastream gives us back the time in a different format:
        expect_created = created
        if expect_created.endswith('Z'):  # it does
            # strip of the Z and any final zeros
            expect_created = expect_created.rstrip('Z0')
            # strip the decimal if it got that far
            expect_created = expect_created.rstrip('.')
            # and put back the Z
            expect_created += 'Z'

        r = self.rest_api.purgeDatastream(self.pid, ds['id'],
                                            logMessage="purging text datastream")
        purged = (r.status_code == requests.codes.ok)
        times = r.text
        self.assertTrue(purged)
        self.assert_(expect_created in times,
            'datastream creation date should be returned in list of purged datastreams - expected %s, got %s' % \
            (expect_created, times))
        # log message in audit trail
        r = self.rest_api.getObjectXML(self.pid)
        self.assert_('purging text datastream' in r.text)
        # datastream no longer listed
        r = self.rest_api.listDatastreams(self.pid)
        self.assert_('<datastream dsid="%s"' % ds['id'] not in r.text)

        # NOTE: Fedora bug - attempting to purge a non-existent datastream returns 204?
        # purged = self.rest_api.purgeDatastream(self.pid, "BOGUS",
        #     logMessage="test purging non-existent datastream")
        # self.assertFalse(purged)

        self.assertRaises(RequestFailed, self.rest_api.purgeDatastream, "bogus:pid",
            "BOGUS", logMessage="test purging non-existent datastream from non-existent object")
        # also test purging specific versions of a datastream ?

        # attempt to purge a version that doesn't exist
        (added, dsprofile), ds = self._add_text_datastream()
        tomorrow = datetime.now(tzutc()) + timedelta(1)
        r = self.rest_api.purgeDatastream(self.pid, ds['id'],
                                        startDT=datetime_to_fedoratime(tomorrow),
                                        logMessage="purging text datastream")
        success = (r.status_code == requests.codes.ok)
        times = r.text
        # no errors, no versions purged
        self.assertTrue(success)
        self.assertEqual('[]', times)

    def test_purgeObject(self):
        obj = load_fixture_data('basic-object.foxml')
        r = self.rest_api.ingest(obj)
        pid = r.text
        r = self.rest_api.purgeObject(pid)
        purged = (r.status_code == requests.codes.ok)
        self.assertTrue(purged)

        # NOTE: fedora doesn't notice the object has been purged right away
        sleep(7)    # 5-6 was fastest this worked; padding to avoid spurious failures
        self.assertRaises(Exception, self.rest_api.getObjectProfile, pid)

        # bad pid
        self.assertRaises(RequestFailed, self.rest_api.purgeObject, "bogus:pid")

    def test_purgeRelationship(self):
        # add relation to purg
        self.rest_api.addRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                      predicate=force_text(modelns.hasModel),
                                      object='info:fedora/pid:123')

        print(self.pid)
        print(force_text(self.pid))
        print(type(self.pid))
        print(self.fedora_fixtures_ingested)

        purged = self.rest_api.purgeRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                                 force_text(modelns.hasModel),
                                                 'info:fedora/pid:123')
        self.assertEqual(purged, True)

        # purge non-existent rel on valid pid
        purged = self.rest_api.purgeRelationship(self.pid, 'info:fedora/%s' % self.pid,
                                                 self.rel_owner, 'johndoe', isLiteral=True)
        self.assertFalse(purged)

        # bogus pid
        self.assertRaises(RequestFailed, self.rest_api.purgeRelationship, "bogus:pid",
                          'info:fedora/bogus:pid', self.rel_owner, "johndoe", True)

    def test_setDatastreamState(self):
        # in Fedora 3.5, Fedora returns a BadRequest when we attempt to
        # mark DC as inactive (probably reasonable); testing on a
        # non-required datastream instead.
        (added, dsprofile), ds = self._add_text_datastream()
        set_state = self.rest_api.setDatastreamState(self.pid, "TEXT", "I")
        self.assertTrue(set_state)

        # get datastream to confirm change
        r = self.rest_api.getDatastream(self.pid, "TEXT")
        self.assert_('<dsState>I</dsState>' in r.text)

        # bad datastream id
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamState,
                          self.pid, "BOGUS", "I")

        # non-existent pid
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamState,
                          "bogus:pid", "DC", "D")

    def test_setDatastreamVersionable(self):
        # In Fedora 3.5, Fedora returns a BadRequest when we attempt
        # to change DC versionable (reasonable?); testing on a
        # non-required datastream instead.
        (added, dsprofile), ds = self._add_text_datastream()
        set_versioned = self.rest_api.setDatastreamVersionable(self.pid, "TEXT", False)
        self.assertTrue(set_versioned)

        # get datastream profile to confirm change
        r = self.rest_api.getDatastream(self.pid, "TEXT")
        self.assert_('<dsVersionable>false</dsVersionable>' in r.text)

        # bad datastream id
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamVersionable,
                          self.pid, "BOGUS", False)

        # non-existent pid
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamVersionable,
                          "bogus:pid", "DC", True)

    # utility methods

    def test_upload_string(self):
        data = "Here is some temporary content to upload to fedora."
        upload_id = self.rest_api.upload(data)
        # current format looks like uploaded://####
        pattern = re.compile('uploaded://[0-9]+')
        self.assert_(pattern.match(force_text(upload_id)))

    def test_upload_file(self):
        FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
        FILE.write("Here is some temporary content to upload to fedora.")
        FILE.flush()

        with open(FILE.name, 'rb') as f:
            upload_id = self.rest_api.upload(f)
        # current format looks like uploaded://####
        pattern = re.compile('uploaded://[0-9]+')
        self.assert_(pattern.match(upload_id))
        self.assertTrue(pattern.match(upload_id))

    def test_upload_generator(self):
        # test uploading content from a generator
        def data_generator():
            yield 'line one of text\n'
            yield 'line two of text\n'
            yield 'line three of text\n'

        text_content = ''.join(data_generator())
        content_md5 = md5sum(text_content)
        size = len(text_content)

        upload_id = self.rest_api.upload(data_generator(), size=size, content_type='text/plain')
        pattern = re.compile('uploaded://[0-9]+')
        self.assertTrue(pattern.match(upload_id))

        # check that the *right* content was uploaded by adding
        # a datastream using the computed MD5 and generated upload id
        obj = load_fixture_data('basic-object.foxml')
        response = self.rest_api.ingest(obj)
        pid = response.text
        add_response = self.rest_api.addDatastream(pid, 'text', controlGroup='M',
            dsLocation=upload_id, mimeType='text/plain',
            checksumType='MD5', checksum=content_md5)
        self.assertTrue(add_response.status_code, requests.codes.created)
        # get the content from fedora and confirm it matches what was sent
        dsresponse = self.rest_api.getDatastreamDissemination(pid, 'text')
        self.assertEqual(text_content, dsresponse.text)

        # clean up test object
        self.rest_api.purgeObject(pid)

    def test_retries(self):
        with patch('eulfedora.api.requests.adapters') as mockreq_adapters:
            # retries not specified, retries = None
            REST_API(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)
            # no custom adapter code needed
            mockreq_adapters.HTTPAdapter.assert_not_called()

            # retry value specified
            REST_API(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD,
                     retries=3)
            # adapter should be initialized with max retries option
            mockreq_adapters.HTTPAdapter.assert_called_with(max_retries=3)


class TestAPI_A_LITE(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    def setUp(self):
        super(TestAPI_A_LITE, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.api_a = API_A_LITE(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)

    def testDescribeRepository(self):
        r = self.api_a.describeRepository()
        self.assert_(b'<repositoryName>' in r.content)
        self.assert_(b'<repositoryVersion>' in r.content)
        self.assert_(b'<adminEmail>' in r.content)


class TestResourceIndex(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE
    # relationship predicates for testing
    rel_isMemberOf = "info:fedora/fedora-system:def/relations-external#isMemberOf"
    rel_owner = "info:fedora/fedora-system:def/relations-external#owner"

    def setUp(self):
        super(TestResourceIndex, self).setUp()
        self.risearch = self.repo.risearch

        pid = self.fedora_fixtures_ingested[0]
        self.object = self.repo.get_object(pid)
        # add some rels to query
        self.cmodel = DigitalObject(self.api, "control:TestObject")
        self.object.add_relationship(modelns.hasModel, self.cmodel)
        self.related = DigitalObject(self.api, "foo:123")
        self.object.add_relationship(self.rel_isMemberOf, self.related)
        self.object.add_relationship(self.rel_owner, "testuser")

    def testGetPredicates(self):
        # get all predicates for test object
        predicates = list(self.risearch.get_predicates(self.object.uri, None))
        self.assertTrue(force_text(modelns.hasModel) in predicates)
        self.assertTrue(self.rel_isMemberOf in predicates)
        self.assertTrue(self.rel_owner in predicates)
        # resource
        predicates = list(self.risearch.get_predicates(self.object.uri, self.related.uri))
        self.assertEqual(predicates[0], self.rel_isMemberOf)
        self.assertEqual(len(predicates), 1)
        # literal
        predicates = list(self.risearch.get_predicates(self.object.uri, "'testuser'"))
        self.assertEqual(predicates[0], self.rel_owner)
        self.assertEqual(len(predicates), 1)

    def testGetSubjects(self):
        subjects = list(self.risearch.get_subjects(self.rel_isMemberOf, self.related.uri))
        self.assertEqual(subjects[0], self.object.uri)
        self.assertEqual(len(subjects), 1)

        # no match
        subjects = list(self.risearch.get_subjects(self.rel_isMemberOf, self.object.uri))
        self.assertEqual(len(subjects), 0)

    def testGetObjects(self):
        objects = list(self.risearch.get_objects(self.object.uri, modelns.hasModel))
        self.assert_(self.cmodel.uri in objects)
        # also includes generic fedora-object cmodel

    def test_sparql(self):
        # simple sparql to retrieve our test object
        query = '''SELECT ?obj
        WHERE {
            ?obj <%s> "%s"
        }
        ''' % (self.rel_owner, 'testuser')
        objects = list(self.risearch.sparql_query(query))
        self.assert_({'obj': self.object.uri} in objects)

    def test_custom_errors(self):
        self.assertRaises(UnrecognizedQueryLanguage,
                          self.risearch.find_statements,
                          '* * *', language='bogus')

    def test_count_statements(self):
        # query something unique to our test objects
        q = '* <fedora-rels-ext:isMemberOf> <%s>' % self.related.uri
        total = self.risearch.count_statements(q)
        self.assertEqual(1, total)

