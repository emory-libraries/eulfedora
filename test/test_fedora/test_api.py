#!/usr/bin/env python

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


from datetime import date, datetime, timedelta
from dateutil.tz import tzutc
import httplib
from lxml import etree
import re
from time import sleep
import tempfile
import warnings

from test_fedora.base import FedoraTestCase, load_fixture_data, FEDORA_ROOT_NONSSL,\
                FEDORA_USER, FEDORA_PASSWORD, FEDORA_PIDSPACE
from eulfedora.api import REST_API, API_A_LITE, API_M_LITE, API_M, ResourceIndex, \
     UnrecognizedQueryLanguage
from eulfedora.models import DigitalObject
from eulfedora.rdfns import model as modelns
from eulfedora.util import AuthorizingServerConnection, fedoratime_to_datetime, \
     datetime_to_fedoratime, RequestFailed, ChecksumMismatch
from eulfedora.xml import FEDORA_MANAGE_NS, FEDORA_ACCESS_NS
from testcore import main



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
        ds = {'id' : 'TEXT', 'label' : 'text datastream', 'mimeType' : 'text/plain',
            'controlGroup' : 'M', 'logMessage' : "creating new datastream",
            'checksumType' : 'MD5'}

        added = self.rest_api.addDatastream(self.pid, ds['id'], ds['label'],
            ds['mimeType'], ds['logMessage'], ds['controlGroup'], filename=FILE.name,
            checksumType=ds['checksumType'])
        FILE.close()
        return (added, ds)

    def setUp(self):
        super(TestREST_API, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.opener = AuthorizingServerConnection(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)
        self.rest_api = REST_API(self.opener)
        self.today = datetime.utcnow().date()

    # API-A calls

    def test_findObjects(self):
        # search for current test object  (restrict to current pidspace to avoid bogus failures)
        found, url = self.rest_api.findObjects("ownerId~tester pid~%s:*" % FEDORA_PIDSPACE)
        self.assert_('<result ' in found)
        self.assert_('<resultList>' in found)
        self.assert_('<pid>%s</pid>' % self.pid in found)

        # crazy search that shouldn't match anything
        found = self.rest_api.findObjects("title~supercalifragilistexpi...")
        self.assert_('<objectFields>' not in found)

        # search for everything - get enough results to get a session token
        # - note that current test fedora includes a number of control objects
        found, url = self.rest_api.findObjects("title~*")
        self.assert_('<listSession>' in found)
        self.assert_('<token>' in found)

        # search by terms
        found, url = self.rest_api.findObjects(terms="more dat? in it than a *")
        self.assert_('<pid>%s</pid>' % self.pid in found)

        # NOTE: not testing resumeFind here because it would require parsing the xml
        # for the session token - tested at the server/Repository level

    def test_getDatastreamDissemination(self):
        dc, url = self.rest_api.getDatastreamDissemination(self.pid, "DC")
        self.assert_("<dc:title>A partially-prepared test object</dc:title>" in dc)
        self.assert_("<dc:description>This object has more data" in dc)
        self.assert_("<dc:identifier>%s</dc:identifier>" % self.pid in dc)

        # get server datetime param (the hard way) for testing
        dsprofile_data, url = self.rest_api.getDatastream(self.pid, "DC")
        dsprofile_node = etree.fromstring(dsprofile_data, base_url=url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)', namespaces={'m': FEDORA_MANAGE_NS})
        created = fedoratime_to_datetime(created_s)

        # with date-time param
        postcreate_dc, url = self.rest_api.getDatastreamDissemination(self.pid, "DC",
            asOfDateTime=created + ONE_SEC)
        self.assertEqual(dc, postcreate_dc)    # unchanged within its first sec

        # bogus datastream
        self.assertRaises(Exception, self.rest_api.getDatastreamDissemination,
            self.pid, "BOGUS")

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getDatastreamDissemination,
            "bogus:pid", "BOGUS")

        # return_http_response
        response = self.rest_api.getDatastreamDissemination(self.pid, 'DC', return_http_response=True)
        self.assert_(isinstance(response, httplib.HTTPResponse),
                     'getDatastreamDissemination should return an HTTPResponse when return_http_response is True')
        # datastream content should still be accessible
        self.assertEqual(dc, response.read())

    # NOTE: getDissemination not available in REST API until Fedora 3.3
    def test_getDissemination(self):
        # testing with built-in fedora dissemination
        profile, uri = self.rest_api.getDissemination(self.pid, "fedora-system:3", "viewItemIndex")
        self.assert_('<title>Object Items HTML Presentation</title>' in profile)
        self.assert_(self.pid in profile)

        # return_http_response
        response = self.rest_api.getDissemination(self.pid, "fedora-system:3", "viewItemIndex",
                                                  return_http_response=True)
        self.assert_(isinstance(response, httplib.HTTPResponse),
                     'getDissemination should return an HTTPResponse when return_http_response is True')
        # datastream content should still be accessible
        self.assert_(self.pid in response.read())

    def test_getObjectHistory(self):
        history, url = self.rest_api.getObjectHistory(self.pid)
        self.assert_('<fedoraObjectHistory' in history)
        self.assert_('pid="%s"' % self.pid in history)
        self.assert_('<objectChangeDate>%s' % self.today in history)

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getObjectHistory, "bogus:pid")

    def test_getObjectProfile(self):
        profile, url = self.rest_api.getObjectProfile(self.pid)
        self.assert_('<objectProfile' in profile)
        self.assert_('pid="%s"' % self.pid in profile)
        self.assert_('<objLabel>A partially-prepared test object</objLabel>' in profile)
        self.assert_('<objOwnerId>tester</objOwnerId>' in profile)
        self.assert_('<objCreateDate>%s' % self.today in profile)
        self.assert_('<objLastModDate>%s' % self.today in profile)
        self.assert_('<objState>A</objState>' in profile)
        # unchecked: objDissIndexViewURL, objItemIndexViewURL

        # get server datetime param (the hard way) for testing
        profile_node = etree.fromstring(profile, base_url=url)
        created_s = profile_node.xpath('string(a:objCreateDate)', namespaces={'a': FEDORA_ACCESS_NS})
        created = fedoratime_to_datetime(created_s)

        # with time
        profile_now, url = self.rest_api.getObjectProfile(self.pid,
                        asOfDateTime=created + ONE_SEC)
        # NOTE: profile content is not exactly the same because it includes a datetime attribute
        self.assert_('pid="%s"' % self.pid in profile_now)
        self.assert_('<objLabel>A partially-prepared test object</objLabel>' in profile_now)

        # bogus pid        
        self.assertRaises(Exception, self.rest_api.getObjectHistory, "bogus:pid")

    def test_listDatastreams(self):
        dslist, url = self.rest_api.listDatastreams(self.pid)
        self.assert_('<objectDatastreams' in dslist)        
        self.assert_('<datastream dsid="DC" label="Dublin Core" mimeType="text/xml"' in dslist)

        # bogus pid
        self.assertRaises(Exception, self.rest_api.listDatastreams, "bogus:pid")

        
    def test_listMethods(self):
        methods, url = self.rest_api.listMethods(self.pid)
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
        message, url = self.rest_api.getObjectXML(self.pid)
        self.assert_(ds['logMessage'] in message)
        dslist, url = self.rest_api.listDatastreams(self.pid)
        self.assert_('<datastream dsid="%(id)s" label="%(label)s" mimeType="%(mimeType)s" />'
            % ds  in dslist)
        ds_profile, url = self.rest_api.getDatastream(self.pid, ds['id'])
        self.assert_('dsID="%s" ' % ds['id'] in ds_profile)
        self.assert_('<dsLabel>%s</dsLabel>' % ds['label'] in ds_profile)
        self.assert_('<dsVersionID>%s.0</dsVersionID>' % ds['id'] in ds_profile)
        self.assert_('<dsCreateDate>%s' % self.today in ds_profile)
        self.assert_('<dsState>A</dsState>' in ds_profile)
        self.assert_('<dsMIME>%s</dsMIME>' % ds['mimeType'] in ds_profile)
        self.assert_('<dsControlGroup>%s</dsControlGroup>' % ds['controlGroup'] in ds_profile)
        self.assert_('<dsVersionable>true</dsVersionable>' in ds_profile)

        # content returned from fedora should be exactly what we started with
        ds_content, url = self.rest_api.getDatastreamDissemination(self.pid, ds['id'])
        self.assertEqual(self.TEXT_CONTENT, ds_content)

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
        self.assertRaises(RequestFailed, self.rest_api.addDatastream, 'bogus:pid',
                          'TEXT', 'text datastream',
                          mimeType='text/plain', logMessage='creating new datastream',
                          controlGroup='M', filename=FILE.name)
        FILE.close()

    def test_compareDatastreamChecksum(self):
        # create datastream with checksum
        (added, ds) = self._add_text_datastream()        
        ds_info, pid = self.rest_api.compareDatastreamChecksum(self.pid, ds['id'])
        self.assert_('<dsChecksum>bfe1f7b3410d1e86676c4f7af2a84889</dsChecksum>' in ds_info)
        # FIXME: how to test that checksum has actually been checked?

        # check for log message in audit trail
        xml, url = self.rest_api.getObjectXML(self.pid)
        self.assert_(ds['logMessage'] in xml)

    def test_export(self):
        export, url = self.rest_api.export(self.pid)
        self.assert_('<foxml:datastream' in export)
        self.assert_('PID="%s"' % self.pid in export)
        self.assert_('<foxml:property' in export)
        self.assert_('<foxml:datastream ID="DC" ' in export)

        # default 'context' is public; also test migrate & archive
        # FIXME/TODO: add more datastreams/versions so export formats differ ?

        export, url = self.rest_api.export(self.pid, context="migrate")
        self.assert_('<foxml:datastream' in export)

        export, url = self.rest_api.export(self.pid, context="archive")
        self.assert_('<foxml:datastream' in export)

        # bogus id
        self.assertRaises(Exception, self.rest_api.export, "bogus:pid")

    def test_getDatastream(self):
        ds_profile, url = self.rest_api.getDatastream(self.pid, "DC")
        self.assert_('<datastreamProfile' in ds_profile)
        self.assert_('pid="%s"' % self.pid in ds_profile)
        self.assert_('dsID="DC" ' in ds_profile)
        self.assert_('<dsLabel>Dublin Core</dsLabel>' in ds_profile)
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in ds_profile)
        self.assert_('<dsCreateDate>%s' % self.today in ds_profile)
        self.assert_('<dsState>A</dsState>' in ds_profile)
        self.assert_('<dsMIME>text/xml</dsMIME>' in ds_profile)
        self.assert_('<dsControlGroup>X</dsControlGroup>' in ds_profile)
        self.assert_('<dsVersionable>true</dsVersionable>' in ds_profile)

        # get server datetime param (the hard way) for testing
        dsprofile_node = etree.fromstring(ds_profile, base_url=url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)', namespaces={'m': FEDORA_MANAGE_NS})
        created = fedoratime_to_datetime(created_s)

        # with date param
        ds_profile_now, url = self.rest_api.getDatastream(self.pid, "DC",
                        asOfDateTime=created + ONE_SEC)
        # NOTE: contents are not exactly equal because 'now' version includes a dateTime attribute
        self.assert_('<dsLabel>Dublin Core</dsLabel>' in ds_profile_now)
        self.assert_('<dsVersionID>DC.0</dsVersionID>' in ds_profile_now)
        
        # bogus datastream id on valid pid
        self.assertRaises(Exception, self.rest_api.getDatastream, self.pid, "BOGUS")

        # bogus pid
        self.assertRaises(Exception, self.rest_api.getDatastream, "bogus:pid", "DC")
        
    def test_getNextPID(self):
        pids, url = self.rest_api.getNextPID()
        self.assert_('<pidList' in pids)
        self.assert_('<pid>' in pids)

        pids, url = self.rest_api.getNextPID(numPIDs=3, namespace="test-ns")        
        self.assertEqual(3, pids.count("<pid>test-ns:"))        

    def test_getObjectXML(self):
        # update the object so we can look for audit trail in object xml
        added, ds = self._add_text_datastream()   
        objxml, url = self.rest_api.getObjectXML(self.pid)
        self.assert_('<foxml:digitalObject' in objxml)
        self.assert_('<foxml:datastream ID="DC" ' in objxml)
        # audit trail accessible in full xml
        self.assert_('<audit:auditTrail ' in objxml)

        # bogus id
        self.assertRaises(Exception, self.rest_api.getObjectXML, "bogus:pid")

    def test_ingest(self):
        object = load_fixture_data('basic-object.foxml')
        pid = self.rest_api.ingest(object)
        self.assertTrue(pid)
        self.rest_api.purgeObject(pid)

        # test ingesting with log message
        pid = self.rest_api.ingest(object, "this is my test ingest message")
        # ingest message is stored in AUDIT datastream
        # - can currently only be accessed by retrieving entire object xml
        xml, url = self.rest_api.getObjectXML(pid)
        self.assertTrue("this is my test ingest message" in xml)
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
        updated, msg = self.rest_api.modifyDatastream(self.pid, ds['id'], "text datastream (modified)",
            mimeType="text/other", logMessage="modifying TEXT datastream", content=open(FILE.name))
        self.assertTrue(updated)
        # log message in audit trail
        xml, url = self.rest_api.getObjectXML(self.pid)
        self.assert_('modifying TEXT datastream' in xml)

        ds_profile, url = self.rest_api.getDatastream(self.pid, ds['id'])
        self.assert_('<dsLabel>text datastream (modified)</dsLabel>' in ds_profile)
        self.assert_('<dsVersionID>%s.1</dsVersionID>' % ds['id'] in ds_profile)
        self.assert_('<dsState>A</dsState>' in ds_profile)
        self.assert_('<dsMIME>text/other</dsMIME>' in ds_profile)  
        
        content, url = self.rest_api.getDatastreamDissemination(self.pid, ds['id'])
        self.assertEqual(content, new_text)       

        # modify DC (inline xml) by string
        new_dc = """<oai_dc:dc
            xmlns:dc='http://purl.org/dc/elements/1.1/'
            xmlns:oai_dc='http://www.openarchives.org/OAI/2.0/oai_dc/'>
          <dc:title>Test-Object</dc:title>
          <dc:description>modified!</dc:description>
        </oai_dc:dc>"""
        updated, msg = self.rest_api.modifyDatastream(self.pid, "DC", "Dublin Core",
            mimeType="text/xml", logMessage="updating DC", content=new_dc)
        self.assertTrue(updated)
        dc, url = self.rest_api.getDatastreamDissemination(self.pid, "DC")
        # fedora changes whitespace in xml, so exact test fails
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
        modified = self.rest_api.modifyObject(self.pid, "modified test object", "testuser",
            "I", "testing modify object")
        self.assertTrue(modified)
        # log message in audit trail
        xml, url = self.rest_api.getObjectXML(self.pid)
        self.assert_('testing modify object' in xml)
        
        profile, xml = self.rest_api.getObjectProfile(self.pid)
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
        if expect_created.endswith('Z'): # it does
            # strip of the Z and any final zeros
            expect_created = expect_created.rstrip('Z0')
            # strip the decimal if it got that far
            expect_created = expect_created.rstrip('.')
            # and put back the Z
            expect_created += 'Z'

        purged, times = self.rest_api.purgeDatastream(self.pid, ds['id'],
                                            logMessage="purging text datastream")
        self.assertTrue(purged)
        self.assert_(expect_created in times,
            'datastream creation date should be returned in list of purged datastreams - expected %s, got %s' % \
            (expect_created, times))
        # log message in audit trail
        xml, url = self.rest_api.getObjectXML(self.pid)
        self.assert_('purging text datastream' in xml)
        # datastream no longer listed
        dslist, url = self.rest_api.listDatastreams(self.pid)
        self.assert_('<datastream dsid="%s"' % ds['id'] not in dslist)

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
        success, times = self.rest_api.purgeDatastream(self.pid, ds['id'],
                                        startDT=datetime_to_fedoratime(tomorrow),
                                        logMessage="purging text datastream")
        # no errors, no versions purged
        self.assertTrue(success)
        self.assertEqual('[]', times)

    def test_purgeObject(self):
        object = load_fixture_data('basic-object.foxml')
        pid = self.rest_api.ingest(object)        
        purged, message = self.rest_api.purgeObject(pid)
        self.assertTrue(purged)

        # NOTE: fedora doesn't notice the object has been purged right away
        sleep(7)    # 5-6 was fastest this worked; padding to avoid spurious failures
        self.assertRaises(Exception, self.rest_api.getObjectProfile, pid)

        # bad pid
        self.assertRaises(RequestFailed, self.rest_api.purgeObject, "bogus:pid")

    def test_setDatastreamState(self):
        set_state = self.rest_api.setDatastreamState(self.pid, "DC", "I")
        self.assertTrue(set_state)

        # get datastream to confirm change
        ds_profile, url = self.rest_api.getDatastream(self.pid, "DC")
        self.assert_('<dsState>I</dsState>' in ds_profile)

        # bad datastream id
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamState,
                          self.pid, "BOGUS", "I")

        # non-existent pid
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamState,
                          "bogus:pid", "DC", "D")

    def test_setDatastreamVersionable(self):
        set_versioned = self.rest_api.setDatastreamVersionable(self.pid, "DC", False)
        self.assertTrue(set_versioned)

        # get datastream profile to confirm change
        ds_profile, url = self.rest_api.getDatastream(self.pid, "DC")
        self.assert_('<dsVersionable>false</dsVersionable>' in ds_profile)

        # bad datastream id
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamVersionable,
                          self.pid, "BOGUS", False)

        # non-existent pid
        self.assertRaises(RequestFailed, self.rest_api.setDatastreamVersionable,
                          "bogus:pid", "DC", True)


class TestAPI_A_LITE(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    def setUp(self):
        super(TestAPI_A_LITE, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.opener = AuthorizingServerConnection(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)
        self.api_a = API_A_LITE(self.opener)

    def testDescribeRepository(self):
        desc, url = self.api_a.describeRepository()
        self.assert_('<repositoryName>' in desc)
        self.assert_('<repositoryVersion>' in desc)
        self.assert_('<adminEmail>' in desc)


class TestAPI_M_LITE(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    def setUp(self):
        super(TestAPI_M_LITE, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.api_m = API_M_LITE(self.opener)

    def testUploadString(self):
        data = "Here is some temporary content to upload to fedora."
        upload_id = self.api_m.upload(data)
        # current format looks like uploaded://####
        pattern = re.compile('uploaded://[0-9]+')
        self.assert_(pattern.match(upload_id))

    def testUploadFile(self):
        FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
        FILE.write("Here is some temporary content to upload to fedora.")
        FILE.flush()

        with open(FILE.name, 'rb') as f:
            upload_id = self.api_m.upload(f)
        # current format looks like uploaded://####
        pattern = re.compile('uploaded://[0-9]+')
        self.assert_(pattern.match(upload_id))


# NOTE: to debug soap, uncomment these lines
#from soaplib.client import debug
#debug(True)

class TestAPI_M(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    # relationship predicates for testing
    rel_isMemberOf = "info:fedora/fedora-system:def/relations-external#isMemberOf"
    rel_owner = "info:fedora/fedora-system:def/relations-external#owner"

    def setUp(self):
        super(TestAPI_M, self).setUp()
        self.pid = self.fedora_fixtures_ingested[0]
        self.api_m = API_M(self.opener)
        self.opener = AuthorizingServerConnection(FEDORA_ROOT_NONSSL, FEDORA_USER, FEDORA_PASSWORD)
        self.rest_api = REST_API(self.opener)

        # get fixture ingest time from the server the hard way for testing
        dsprofile_data, url = self.rest_api.getDatastream(self.pid, "DC")
        dsprofile_node = etree.fromstring(dsprofile_data, base_url=url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)',
                                         namespaces={'m': FEDORA_MANAGE_NS})
        self.ingest_time = fedoratime_to_datetime(created_s)
        
    def test_addRelationship(self):
        # rel to resource
        added = self.api_m.addRelationship(self.pid, unicode(modelns.hasModel), "info:fedora/pid:123", False)
        self.assertTrue(added)
        rels, url = self.rest_api.getDatastreamDissemination(self.pid, "RELS-EXT")
        self.assert_('<hasModel' in rels)
        self.assert_('rdf:resource="info:fedora/pid:123"' in rels)

        # literal
        added = self.api_m.addRelationship(self.pid, self.rel_owner, "johndoe", True)
        self.assertTrue(added)
        rels, url = self.rest_api.getDatastreamDissemination(self.pid, "RELS-EXT")
        self.assert_('<owner' in rels)
        self.assert_('>johndoe<' in rels)

        # bogus pid
        self.assertRaises(Exception, self.api_m.addRelationship,
            "bogus:pid", self.rel_owner, "johndoe", True)

    def test_getRelationships(self):
        # add relations
        self.api_m.addRelationship(self.pid, unicode(modelns.hasModel), "info:fedora/pid:123", False)
        self.api_m.addRelationship(self.pid, self.rel_owner, "johndoe", True)

        response = self.api_m.getRelationships(self.pid, unicode(modelns.hasModel))
        rels = response.relationships

        self.assertEqual(2, len(rels))  # includes fedora-system cmodel
        self.assertEqual(rels[0].subject, 'info:fedora/' + self.pid)
        self.assertEqual(rels[0].predicate, unicode(modelns.hasModel))
        cmodels = [rels[0].object, rels[1].object]
        self.assert_('info:fedora/fedora-system:FedoraObject-3.0' in cmodels)
        self.assert_('info:fedora/pid:123' in cmodels)

        response = self.api_m.getRelationships(self.pid, self.rel_owner)
        rels = response.relationships
        self.assertEqual(1, len(rels))
        self.assertEqual(rels[0].subject, 'info:fedora/' + self.pid)
        self.assertEqual(rels[0].predicate, self.rel_owner)
        self.assertEqual(rels[0].object, "johndoe")

    def test_purgeRelationship(self):
        # add relation to purge
        self.api_m.addRelationship(self.pid, unicode(modelns.hasModel), "info:fedora/pid:123", False)
        
        purged = self.api_m.purgeRelationship(self.pid, unicode(modelns.hasModel), "info:fedora/pid:123", False)
        self.assertEqual(purged, True)

        # purge non-existent rel on valid pid
        purged = self.api_m.purgeRelationship(self.pid, self.rel_owner, "johndoe", True)
        self.assertFalse(purged)

        # bogus pid
        self.assertRaises(Exception, self.api_m.purgeRelationship, "bogus:pid",
            self.rel_owner, "johndoe", True)        

    def test_getDatastreamHistory(self):
        history = self.api_m.getDatastreamHistory(self.pid, "DC")
        self.assertEqual(1, len(history.datastreams))
        dc_info = history.datastreams[0]
        self.assertEqual('X', dc_info.controlGroup)
        self.assertEqual('DC', dc_info.ID)
        self.assertEqual('DC.0', dc_info.versionID)
         # altIDs unused
        self.assertEqual('Dublin Core', dc_info.label)
        self.assertTrue(dc_info.versionable)
        self.assertEqual("text/xml", dc_info.MIMEType)
        # formatURI not set in test fixture
        self.assertEqual(self.ingest_time, dc_info.createDate) 
        self.assert_(dc_info.size) # size should be non-zero - number comparison not reliable
        self.assertEqual('A', dc_info.state) 
        # location, checksumType, and checksum not set in current fixture
        
        # modify DC so there are multiple versions        
        new_dc = """<oai_dc:dc
            xmlns:dc='http://purl.org/dc/elements/1.1/'
            xmlns:oai_dc='http://www.openarchives.org/OAI/2.0/oai_dc/'>
          <dc:title>Test-Object</dc:title>
          <dc:description>modified!</dc:description>
        </oai_dc:dc>"""
        self.rest_api.modifyDatastream(self.pid, "DC", "DCv2Dublin Core",
            mimeType="text/xml", logMessage="updating DC", content=new_dc)
        history = self.api_m.getDatastreamHistory(self.pid, "DC")
        self.assertEqual(2, len(history.datastreams))
        self.assertEqual('DC.1', history.datastreams[0].versionID)      # newest version is first
        self.assertNotEqual(history.datastreams[0].createDate, history.datastreams[1].createDate)

        # bogus datastream
        self.assertEqual(None, self.api_m.getDatastreamHistory(self.pid, "BOGUS"))

        # bogus pid
        self.assertRaises(Exception, self.api_m.getDatastreamHistory, "bogus:pid", "DC")


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
        self.assertTrue(unicode(modelns.hasModel) in predicates)
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
        objects =  list(self.risearch.get_objects(self.object.uri, modelns.hasModel))
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
        self.assertRaises(UnrecognizedQueryLanguage,  self.risearch.find_statements,
                          '* * *', language='bogus')

    def test_count_statements(self):
        # query something unique to our test objects
        q = '* <fedora-rels-ext:isMemberOf> <%s>' % self.related.uri
        total = self.risearch.count_statements(q)
        self.assertEqual(1, total)


if __name__ == '__main__':
    main()
