#!/usr/bin/env python

# file test_fedora/test_models.py
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
import logging
from lxml import etree
from mock import Mock, patch
import os
from rdflib import URIRef, Graph as RdfGraph, XSD, Literal
from rdflib.namespace import Namespace
import tempfile

from eulfedora import models
from eulfedora.api import ApiFacade
from eulfedora.rdfns import relsext, model as modelns
from eulfedora.util import RequestFailed, fedoratime_to_datetime
from eulfedora.xml import ObjectDatastream, FEDORA_MANAGE_NS
from eulxml.xmlmap.dc import DublinCore

from test_fedora.base import FedoraTestCase, FEDORA_PIDSPACE, FIXTURE_ROOT
from testcore import main

logger = logging.getLogger(__name__)

ONE_SEC = timedelta(seconds=1)

class MyDigitalObject(models.DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:ExampleCModel' % FEDORA_PIDSPACE,
                      'info:fedora/%s:AnotherCModel' % FEDORA_PIDSPACE]

    # extend digital object with datastreams for testing
    text = models.Datastream("TEXT", "Text datastream", defaults={
            'mimetype': 'text/plain',
        })
    extradc = models.XmlDatastream("EXTRADC", "Managed DC XML datastream", DublinCore,
        defaults={
            'mimetype': 'application/xml',
            'versionable': True,
        })
    image = models.FileDatastream('IMAGE', 'managed binary image datastream', defaults={
            'mimetype': 'image/png',
        })

class SimpleDigitalObject(models.DigitalObject):
    CONTENT_MODELS = ['info:fedora/%s:SimpleObject' % FEDORA_PIDSPACE]

    # extend digital object with datastreams for testing
    text = models.Datastream("TEXT", "Text datastream", defaults={
            'mimetype': 'text/plain',
        })
    extradc = models.XmlDatastream("EXTRADC", "Managed DC XML datastream", DublinCore)


TEXT_CONTENT = "Here is some text content for a non-xml datastream."
def _add_text_datastream(obj):    
    # add a text datastream to the current test object
    FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".txt")
    FILE.write(TEXT_CONTENT)
    FILE.flush()
    # info for calling addDatastream, and return
    ds = {  'id' : 'TEXT', 'label' : 'text datastream', 'mimeType' : 'text/plain',
        'controlGroup' : 'M', 'logMessage' : "creating new datastream", 'versionable': False,
        'checksumType' : 'MD5'}
    obj.api.addDatastream(obj.pid, ds['id'], ds['label'],
        ds['mimeType'], ds['logMessage'], ds['controlGroup'], filename=FILE.name,
        checksumType=ds['checksumType'], versionable=ds['versionable'])
    FILE.close()
    


class TestDatastreams(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    def setUp(self):
        super(TestDatastreams, self).setUp()
        self.pid = self.fedora_fixtures_ingested[-1] # get the pid for the last object
        self.obj = MyDigitalObject(self.api, self.pid)

        # add a text datastream to the current test object
        _add_text_datastream(self.obj)

        # get fixture ingest time from the server (the hard way) for testing
        dsprofile_data, url = self.obj.api.getDatastream(self.pid, "DC")
        dsprofile_node = etree.fromstring(dsprofile_data, base_url=url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)',
                                         namespaces={'m': FEDORA_MANAGE_NS})
        self.ingest_time = fedoratime_to_datetime(created_s)


    def test_get_ds_content(self):
        dc = self.obj.dc.content
        self.assert_(isinstance(self.obj.dc, models.XmlDatastreamObject))
        self.assert_(isinstance(dc, DublinCore))
        self.assertEqual(dc.title, "A partially-prepared test object")
        self.assertEqual(dc.identifier, self.pid)

        self.assert_(isinstance(self.obj.text, models.DatastreamObject))
        self.assertEqual(self.obj.text.content, TEXT_CONTENT)

    def test_get_ds_info(self):
        self.assertEqual(self.obj.dc.label, "Dublin Core")
        self.assertEqual(self.obj.dc.mimetype, "text/xml")
        self.assertEqual(self.obj.dc.state, "A")
        self.assertEqual(self.obj.dc.versionable, True) 
        self.assertEqual(self.obj.dc.control_group, "X")
        # there may be micro-second variation between these two
        # ingest/creation times, but they should probably be less than
        # a second apart
        try:
            self.assertAlmostEqual(self.ingest_time, self.obj.dc.created,
                                   delta=ONE_SEC)
        except TypeError:
            # delta keyword unavailable before python 2.7
            self.assert_(abs(self.ingest_time - self.obj.dc.created) < ONE_SEC)

        # short-cut to datastream size
        self.assertEqual(self.obj.dc.info.size, self.obj.dc.size)

        self.assertEqual(self.obj.text.label, "text datastream")
        self.assertEqual(self.obj.text.mimetype, "text/plain")
        self.assertEqual(self.obj.text.state, "A")
        self.assertEqual(self.obj.text.versionable, False)
        self.assertEqual(self.obj.text.control_group, "M")
        try:
            self.assertAlmostEqual(self.ingest_time, self.obj.text.created,
                                   delta=ONE_SEC)
        except TypeError:
            # delta keyword unavailable before python 2.7
            self.assert_(abs(self.ingest_time - self.obj.text.created) < ONE_SEC)

        # bootstrap info from defaults for a new object
        newobj = MyDigitalObject(self.api)
        self.assertEqual('Text datastream', newobj.text.label,
             'default label should be set on new datastream')
        self.assertEqual('text/plain', newobj.text.mimetype,
             'default label should be set on new datastream')
        self.assertEqual('MD5', newobj.text.checksum_type,
             'default checksum type should be set on new datastream')

    def test_savedatastream(self):
        new_text = "Here is some totally new text content."
        self.obj.text.content = new_text
        self.obj.text.label = "new ds label"
        self.obj.text.mimetype = "text/other"
        self.obj.text.versionable = False
        self.obj.text.state = "I"
        self.obj.text.format = "some.format.uri"
        saved = self.obj.text.save("changed text")
        self.assertTrue(saved, "saving TEXT datastream should return true")
        self.assertEqual(self.obj.text.content, new_text)
        # compare with the datastream pulled directly from Fedora
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.text.id)
        self.assertEqual(data, new_text)
        dsinfo, url = self.obj.api.getDatastream(self.pid, self.obj.text.id)
        self.assert_("<dsLabel>new ds label</dsLabel>" in dsinfo)
        self.assert_("<dsMIME>text/other</dsMIME>" in dsinfo)
        self.assert_("<dsVersionable>false</dsVersionable>" in dsinfo)
        self.assert_("<dsState>I</dsState>" in dsinfo)
        self.assert_("<dsFormatURI>some.format.uri</dsFormatURI>" in dsinfo)
        # look for log message ?

        self.obj.dc.content.title = "this is a new title"
        saved = self.obj.dc.save("changed DC title")
        self.assertTrue(saved, "saving DC datastream should return true")
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.dc.id)
        self.assert_("<dc:title>this is a new title</dc:title>" in data)

    def test_save_by_location(self):
        file_uri = 'file:///tmp/rsk-test.txt'

        # since we can't put or guarantee a test file on the fedora server,
        # patch the api with Mock to check api call
        with patch.object(ApiFacade, 'modifyDatastream') as mock_mod_ds:
            mock_mod_ds.return_value = (True, 'saved')
            
            self.obj.text.ds_location = file_uri
            self.obj.text.content = 'this content should be ignored'
            logmsg = 'text content from file uri'
            saved = self.obj.text.save(logmsg)
            self.assertTrue(saved)
            mock_mod_ds.assert_called_with(self.obj.pid, self.obj.text.id,
                                          mimeType='text/plain', dsLocation=file_uri,
                                          logMessage=logmsg)
            self.assertEqual(None, self.obj.text.ds_location,
                             'ds_location should be None after successful save')

            # simulate save failure (without an exception)
            mock_mod_ds.return_value = (False, 'not saved')
            self.obj.text.ds_location = file_uri
            saved = self.obj.text.save(logmsg)
            self.assertFalse(saved)
            self.assertNotEqual(None, self.obj.text.ds_location,
                             'ds_location should not be None after failed save')

        # purge ds and test addDatastream
        self.obj.api.purgeDatastream(self.obj.pid, self.obj.text.id)
        # load a new version that knows text ds doesn't exist
        obj = MyDigitalObject(self.api, self.pid)
        
        with patch.object(ApiFacade, 'addDatastream') as mock_add_ds:
            mock_add_ds.return_value = (True, 'added')
            
            obj.text.ds_location = file_uri
            obj.text.content = 'this content should be ignored'
            logmsg = 'text content from file uri'
            saved = obj.text.save(logmsg)
            self.assertTrue(saved)
            mock_add_ds.assert_called_with(self.obj.pid, self.obj.text.id,
                                          mimeType='text/plain', dsLocation=file_uri,
                                          logMessage=logmsg, controlGroup='M')
            self.assertEqual(None, obj.text.ds_location,
                             'ds_location should be None after successful save (add)')

                    

    def test_ds_isModified(self):
        self.assertFalse(self.obj.text.isModified(), "isModified should return False for unchanged DC datastream")
        self.assertFalse(self.obj.dc.isModified(), "isModified should return False for unchanged DC datastream")

        self.obj.text.label = "next text label"
        self.assertTrue(self.obj.text.isModified(), "isModified should return True when text datastream label has been updated")

        self.obj.dc.content.description = "new datastream contents"
        self.assertTrue(self.obj.dc.isModified(), "isModified should return True when DC datastream content has changed")

        self.obj.text.save()
        self.obj.dc.save()
        self.assertFalse(self.obj.text.isModified(), "isModified should return False after text datastream has been saved")
        self.assertFalse(self.obj.dc.isModified(), "isModified should return False after DC datastream has been saved")

    def test_rdf_datastream(self):
        # add a relationship to test RELS-EXT/rdf datastreams        
        foo123 = "info:fedora/foo:123"
        self.obj.add_relationship(relsext.isMemberOf, foo123)
        
        self.assert_(isinstance(self.obj.rels_ext, models.RdfDatastreamObject))
        self.assert_(isinstance(self.obj.rels_ext.content, RdfGraph))
        self.assert_((self.obj.uriref, relsext.isMemberOf, URIRef(foo123)) in
                     self.obj.rels_ext.content)

    def test_file_datastream(self):
        # confirm the image datastream does not exist, so we can test adding it
        self.assertFalse(self.obj.image.exists)

        # add file datastream to test object
        filename = os.path.join(FIXTURE_ROOT, 'test.png')
        with open(filename) as imgfile:
            self.obj.image.content = imgfile
            imgsaved = self.obj.save()

        self.assertTrue(imgsaved)
        # datastream should exist now
        self.assertTrue(self.obj.image.exists)
        # file content should be reset
        self.assertEqual(None, self.obj.image._raw_content())
        self.assertFalse(self.obj.image.isModified(),
                         "isModified should return False for image datastream after it has been saved")
        
        # access via file datastream descriptor
        self.assert_(isinstance(self.obj.image, models.FileDatastreamObject))
        self.assertEqual(self.obj.image.content.read(), open(filename).read())

        # update via descriptor
        new_file = os.path.join(FIXTURE_ROOT, 'test.jpeg')
        self.obj.image.content = open(new_file)
        self.obj.image.checksum='aaa'
        self.assertTrue(self.obj.image.isModified())
        
        #Saving with incorrect checksum should fail.
        expected_error = None
        try:
            self.obj.save()
        except models.DigitalObjectSaveFailure as e:
            #Error should go here
            expected_error = e
        self.assert_(str(expected_error).endswith('successfully backed out '), 'Incorrect checksum should back out successfully.') 
        
        #Now try with correct checksum
        self.obj.image.content = open(new_file)
        self.obj.image.checksum='57d5eb11a19cf6f67ebd9e8673c9812e'
        return_status = self.obj.save()
        self.fedora_fixtures_ingested.append(self.obj.pid)
        self.assertEqual(True, return_status)

        # grab a new copy from fedora, confirm contents match
        obj = MyDigitalObject(self.api, self.pid)
        self.assertEqual(obj.image.content.read(), open(new_file).read())
        self.assertEqual(obj.image.checksum, '57d5eb11a19cf6f67ebd9e8673c9812e')

    def test_undo_last_save(self):
        # test undoing profile and content changes        
        
        # unversioned datastream
        self.obj.text.label = "totally new label"
        self.obj.text.content = "and totally new content, too"
        self.obj.text.save()
        self.append_test_pid(self.obj.pid)
        self.assertTrue(self.obj.text.undo_last_save())
        history = self.obj.api.getDatastreamHistory(self.obj.pid, self.obj.text.id)
        self.assertEqual("text datastream", history.datastreams[0].label)
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.text.id)
        self.assertEqual(TEXT_CONTENT, data)
        
        # versioned datastream
        self.obj.dc.label = "DC 2.0"
        self.obj.dc.title = "my new DC"
        self.obj.dc.save()
        self.assertTrue(self.obj.dc.undo_last_save())
        history = self.obj.api.getDatastreamHistory(self.obj.pid, self.obj.dc.id)
        self.assertEqual(1, len(history.datastreams))  # new datastream added, then removed - back to 1 version
        self.assertEqual("Dublin Core", history.datastreams[0].label)
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.dc.id)
        self.assert_('<dc:title>A partially-prepared test object</dc:title>' in data)

        # unversioned - profile change only
        self.obj = MyDigitalObject(self.api, self.pid)
        self.obj.text.label = "totally new label"
        self.obj.text.save()
        self.assertTrue(self.obj.text.undo_last_save())
        history = self.obj.api.getDatastreamHistory(self.obj.pid, self.obj.text.id)
        self.assertEqual("text datastream", history.datastreams[0].label)
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.text.id)
        self.assertEqual(TEXT_CONTENT, data)

    def test_get_chunked_content(self):
        # get chunks - chunksize larger than entire text content
        chunks = list(self.obj.text.get_chunked_content(1024))
        self.assertEqual(self.obj.text.content, chunks[0])
        # smaller chunksize
        chunks = list(self.obj.text.get_chunked_content(10))
        self.assertEqual(self.obj.text.content[:10], chunks[0])
        self.assertEqual(self.obj.text.content[10:20], chunks[1])
        
class TestNewObject(FedoraTestCase):
    pidspace = FEDORA_PIDSPACE

    def test_basic_ingest(self):
        self.repo.default_pidspace = self.pidspace
        obj = self.repo.get_object(type=MyDigitalObject)
        self.assertFalse(isinstance(obj.pid, basestring))
        obj.save()
        self.append_test_pid(obj.pid)

        self.assertTrue(isinstance(obj.pid, basestring))
        self.append_test_pid(obj.pid)
        
        fetched = self.repo.get_object(obj.pid, type=MyDigitalObject)
        self.assertEqual(fetched.dc.content.identifier, obj.pid)

    def test_ingest_content_uri(self):
        obj = self.repo.get_object(type=MyDigitalObject)
        obj.pid = 'test:1'
        obj.text.ds_location = 'file:///tmp/some/local/file.txt'
        # don't actually save, since we can't put a test file on the fedora test server
        foxml = obj._build_foxml_doc()
        # inspect TEXT datastream contentLocation in the generated foxml
        text_dsloc = foxml.xpath('.//f:datastream[@ID="TEXT"]/' +
                                 'f:datastreamVersion/f:contentLocation',
                                 namespaces={'f': obj.FOXML_NS})[0]
        
        self.assertEqual(obj.text.ds_location, text_dsloc.get('REF'))
        self.assertEqual('URL', text_dsloc.get('TYPE'))


    def test_modified_profile(self):
        obj = self.repo.get_object(type=MyDigitalObject)
        obj.label = 'test label'
        obj.owner = 'tester'
        obj.state = 'I'
        obj.save()
        self.append_test_pid(obj.pid)

        self.assertEqual(obj.label, 'test label')
        self.assertEqual(obj.owner, 'tester')
        self.assertEqual(obj.state, 'I')

        fetched = self.repo.get_object(obj.pid, type=MyDigitalObject)
        self.assertEqual(fetched.label, 'test label')
        self.assertEqual(fetched.owner, 'tester')
        self.assertEqual(fetched.state, 'I')

    def test_multiple_owners(self):
        obj = self.repo.get_object(type=MyDigitalObject)
        obj.owner = 'thing1, thing2'
        self.assert_(isinstance(obj.owners, list))
        self.assertEqual(['thing1', 'thing2'], obj.owners)

        obj.owner = ' thing1,   thing2 '
        self.assertEqual(['thing1', 'thing2'], obj.owners)
        


    def test_default_datastreams(self):
        """If we just create and save an object, verify that DigitalObject
        initializes its datastreams appropriately."""

        obj = self.repo.get_object(type=MyDigitalObject)
        obj.save()
        self.append_test_pid(obj.pid)

        # verify some datastreams on the original object

        # fedora treats dc specially
        self.assertEqual(obj.dc.label, 'Dublin Core')
        self.assertEqual(obj.dc.mimetype, 'text/xml')
        self.assertEqual(obj.dc.versionable, False)
        self.assertEqual(obj.dc.state, 'A')
        self.assertEqual(obj.dc.format, 'http://www.openarchives.org/OAI/2.0/oai_dc/')
        self.assertEqual(obj.dc.control_group, 'X')
        self.assertEqual(obj.dc.content.identifier, obj.pid) # fedora sets this automatically

        # test rels-ext as an rdf datastream
        self.assertEqual(obj.rels_ext.label, 'External Relations')
        self.assertEqual(obj.rels_ext.mimetype, 'application/rdf+xml')
        self.assertEqual(obj.rels_ext.versionable, False)
        self.assertEqual(obj.rels_ext.state, 'A')
        self.assertEqual(obj.rels_ext.format, 'info:fedora/fedora-system:FedoraRELSExt-1.0')
        self.assertEqual(obj.rels_ext.control_group, 'X')

        self.assertTrue(isinstance(obj.rels_ext.content, RdfGraph))
        self.assert_((obj.uriref, modelns.hasModel, URIRef(MyDigitalObject.CONTENT_MODELS[0])) in
                     obj.rels_ext.content)
        self.assert_((obj.uriref, modelns.hasModel, URIRef(MyDigitalObject.CONTENT_MODELS[0])) in
                     obj.rels_ext.content)

        # test managed xml datastreams
        self.assertEqual(obj.extradc.label, 'Managed DC XML datastream')
        self.assertEqual(obj.extradc.mimetype, 'application/xml')
        self.assertEqual(obj.extradc.versionable, True)
        self.assertEqual(obj.extradc.state, 'A')
        self.assertEqual(obj.extradc.control_group, 'M')
        self.assertTrue(isinstance(obj.extradc.content, DublinCore))

        # verify those datastreams on a new version fetched fresh from the
        # repo

        fetched = self.repo.get_object(obj.pid, type=MyDigitalObject)

        self.assertEqual(fetched.dc.label, 'Dublin Core')
        self.assertEqual(fetched.dc.mimetype, 'text/xml')
        self.assertEqual(fetched.dc.versionable, False)
        self.assertEqual(fetched.dc.state, 'A')
        self.assertEqual(fetched.dc.format, 'http://www.openarchives.org/OAI/2.0/oai_dc/')
        self.assertEqual(fetched.dc.control_group, 'X')
        self.assertEqual(fetched.dc.content.identifier, fetched.pid)

        self.assertEqual(fetched.rels_ext.label, 'External Relations')
        self.assertEqual(fetched.rels_ext.mimetype, 'application/rdf+xml')
        self.assertEqual(fetched.rels_ext.versionable, False)
        self.assertEqual(fetched.rels_ext.state, 'A')
        self.assertEqual(fetched.rels_ext.format, 'info:fedora/fedora-system:FedoraRELSExt-1.0')
        self.assertEqual(fetched.rels_ext.control_group, 'X')

        self.assert_((obj.uriref, modelns.hasModel, URIRef(MyDigitalObject.CONTENT_MODELS[0])) in
                     fetched.rels_ext.content)
        self.assert_((obj.uriref, modelns.hasModel, URIRef(MyDigitalObject.CONTENT_MODELS[1])) in
                     fetched.rels_ext.content)

        self.assertEqual(fetched.extradc.label, 'Managed DC XML datastream')
        self.assertEqual(fetched.extradc.mimetype, 'application/xml')
        self.assertEqual(fetched.extradc.versionable, True)
        self.assertEqual(fetched.extradc.state, 'A')
        self.assertEqual(fetched.extradc.control_group, 'M')
        self.assertTrue(isinstance(fetched.extradc.content, DublinCore))

    def test_modified_datastreams(self):
        """Verify that we can modify a new object's datastreams before
        ingesting it."""
        obj = MyDigitalObject(self.api, pid=self.getNextPid(), create=True)
        
        # modify content for dc (metadata should be covered by other tests)
        obj.dc.content.description = 'A test object'
        obj.dc.content.rights = 'Rights? Sure, copy our test object.'

        # modify managed xml content (more metadata in text, below)
        obj.extradc.content.description = 'Still the same test object'

        # rewrite info and content for a managed binary datastream
        obj.text.label = 'The outer limits of testing'
        obj.text.mimetype = 'text/x-test'
        obj.text.versionable = True
        obj.text.state = 'I'
        obj.text.format = 'http://example.com/'
        obj.text.content = 'We are controlling transmission.'

        # save and verify in the same object
        obj.save()
        self.append_test_pid(obj.pid)

        self.assertEqual(obj.dc.content.description, 'A test object')
        self.assertEqual(obj.dc.content.rights, 'Rights? Sure, copy our test object.')
        self.assertEqual(obj.extradc.content.description, 'Still the same test object')
        self.assertEqual(obj.text.label, 'The outer limits of testing')
        self.assertEqual(obj.text.mimetype, 'text/x-test')
        self.assertEqual(obj.text.versionable, True)
        self.assertEqual(obj.text.state, 'I')
        self.assertEqual(obj.text.format, 'http://example.com/')
        self.assertEqual(obj.text.content, 'We are controlling transmission.')

        # re-fetch and verify
        fetched = MyDigitalObject(self.api, obj.pid)

        self.assertEqual(fetched.dc.content.description, 'A test object')
        self.assertEqual(fetched.dc.content.rights, 'Rights? Sure, copy our test object.')
        self.assertEqual(fetched.extradc.content.description, 'Still the same test object')
        self.assertEqual(fetched.text.label, 'The outer limits of testing')
        self.assertEqual(fetched.text.mimetype, 'text/x-test')
        self.assertEqual(fetched.text.versionable, True)
        self.assertEqual(fetched.text.state, 'I')
        self.assertEqual(fetched.text.format, 'http://example.com/')
        self.assertEqual(fetched.text.content, 'We are controlling transmission.')

    def test_modify_multiple(self):
        obj = self.repo.get_object(type=MyDigitalObject)
        obj.label = 'test label'
        obj.dc.content.title = 'test dc title'
        obj.image.content = open(os.path.join(FIXTURE_ROOT, 'test.png'))
        obj.save()
        self.append_test_pid(obj.pid)

        # update and save multiple pieces, including filedatastream metadata
        obj.label = 'new label'
        obj.dc.content.title = 'new dc title'
        obj.image.label = 'testimage.png'
        saved = obj.save()
        self.assertTrue(saved)
        updated_obj = self.repo.get_object(obj.pid, type=MyDigitalObject)
        self.assertEqual(obj.label, updated_obj.label)
        self.assertEqual(obj.dc.content.title, updated_obj.dc.content.title)
        self.assertEqual(obj.image.label, updated_obj.image.label)
 
        
    def test_new_file_datastream(self):
        obj = self.repo.get_object(type=MyDigitalObject)
        obj.image.content = open(os.path.join(FIXTURE_ROOT, 'test.png'))
        obj.save()
        self.append_test_pid(obj.pid)

        fetched = self.repo.get_object(obj.pid, type=MyDigitalObject)
        file = open(os.path.join(FIXTURE_ROOT, 'test.png'))
        self.assertEqual(fetched.image.content.read(), file.read())        


class TestDigitalObject(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    pidspace = FEDORA_PIDSPACE

    def setUp(self):
        super(TestDigitalObject, self).setUp()
        self.pid = self.fedora_fixtures_ingested[-1] # get the pid for the last object
        self.obj = MyDigitalObject(self.api, self.pid)
        _add_text_datastream(self.obj)

        # get fixture ingest time from the server (the hard way) for testing
        dsprofile_data, url = self.obj.api.getDatastream(self.pid, "DC")
        dsprofile_node = etree.fromstring(dsprofile_data, base_url=url)
        created_s = dsprofile_node.xpath('string(m:dsCreateDate)',
                                         namespaces={'m': FEDORA_MANAGE_NS})
        self.ingest_time = fedoratime_to_datetime(created_s)


    def test_properties(self):
        self.assertEqual(self.pid, self.obj.pid)
        self.assertTrue(self.obj.uri.startswith("info:fedora/"))
        self.assertTrue(self.obj.uri.endswith(self.pid))

    def test_get_object_info(self):
        self.assertEqual(self.obj.label, "A partially-prepared test object")
        self.assertEqual(self.obj.owner, "tester")
        self.assertEqual(self.obj.state, "A")
        try:
            self.assertAlmostEqual(self.ingest_time, self.obj.created,
                                   delta=ONE_SEC)
        except TypeError:
            # delta keyword unavailable before python 2.7
            self.assert_(abs(self.ingest_time - self.obj.created) < ONE_SEC)

        self.assert_(self.ingest_time < self.obj.modified)

    def test_save_object_info(self):
        self.obj.label = "An updated test object"
        self.obj.owner = "notme"
        self.obj.state = "I"
        saved = self.obj._saveProfile("saving test object profile")
        self.assertTrue(saved, "DigitalObject saveProfile should return True on successful update")
        profile = self.obj.getProfile() # get fresh from fedora to confirm updated
        self.assertEqual(profile.label, "An updated test object")
        self.assertEqual(profile.owner, "notme")
        self.assertEqual(profile.state, "I")
        self.assertNotEqual(profile.created, profile.modified,
                "object create date should not equal modified after updating object profile")

    def test_object_label(self):
        # object label set method has special functionality
        self.obj.label = ' '.join('too long' for i in range(50))
        self.assertEqual(255, len(self.obj.label), 'object label should be truncated to 255 characters')
        self.assertTrue(self.obj.info_modified, 'object info modified when object label has changed')

        self.obj.info_modified = False
        self.obj.label = str(self.obj.label)
        self.assertFalse(self.obj.info_modified,
                         'object info should not be considered modified after setting label to its current value')

    def test_save(self):
        # unmodified object - save should do nothing
        self.obj.save()
        self.append_test_pid(self.obj.pid)

        # modify object profile, datastream content, datastream info
        self.obj.label = "new label"
        self.obj.dc.content.title = "new dublin core title"
        self.obj.text.label = "text content"
        self.obj.text.checksum_type = "MD5"
        self.obj.text.checksum = "avcd"
        
        #Saving with incorrect checksum should fail.
        expected_error = None
        try:
            self.obj.save()
        except models.DigitalObjectSaveFailure as e:
            #Error should go here
            expected_error = e
        self.assert_(str(expected_error).endswith('successfully backed out '), 'Incorrect checksum should back out successfully.') 
        

        # re-initialize the object. do it with a unicode pid to test a regression.
        self.obj = MyDigitalObject(self.api, unicode(self.pid))

        # modify object profile, datastream content, datastream info
        self.obj.label = u"new label\u2014with unicode"
        self.obj.dc.content.title = u"new dublin core title\u2014also with unicode"
        self.obj.text.label = "text content"
        self.obj.text.checksum_type = "MD5"
        self.obj.text.checksum = "1c83260ff729265470c0d349e939c755"
        return_status = self.obj.save()
        
        #Correct checksum should modify correctly.
        self.assertEqual(True, return_status)

        # confirm all changes were saved to fedora
        profile = self.obj.getProfile() 
        self.assertEqual(profile.label, u"new label\u2014with unicode")
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.dc.id)
        self.assert_(u'<dc:title>new dublin core title\u2014also with unicode</dc:title>' in unicode(data, 'utf-8'))
        text_info = self.obj.getDatastreamProfile(self.obj.text.id)
        self.assertEqual(text_info.label, "text content")
        self.assertEqual(text_info.checksum_type, "MD5")
        
        # force an error on saving DC to test backing out text datastream
        self.obj.text.content = "some new text"
        self.obj.dc.content = "this is not dublin core!"    # NOTE: setting xml content like this could change...
        # catch the exception so we can inspect it
        try:
            self.obj.save()
        except models.DigitalObjectSaveFailure, f:
            save_error = f
        self.assert_(isinstance(save_error, models.DigitalObjectSaveFailure))
        self.assertEqual(save_error.obj_pid, self.obj.pid,
            "save failure exception should include object pid %s, got %s" % (self.obj.pid, save_error.obj_pid))
        self.assertEqual(save_error.failure, "DC", )
        self.assertEqual(['TEXT', 'DC'], save_error.to_be_saved)
        self.assertEqual(['TEXT'], save_error.saved)
        self.assertEqual(['TEXT'], save_error.cleaned)
        self.assertEqual([], save_error.not_cleaned)
        self.assertTrue(save_error.recovered)
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.text.id)
        self.assertEqual(TEXT_CONTENT, data)

        # force an error updating the profile, should back out both datastreams
        self.obj = MyDigitalObject(self.api, self.pid)
        self.obj.text.content = "some new text"
        self.obj.dc.content.description = "happy happy joy joy"
        # object label is limited in length - force an error with a label that exceeds it
        # NOTE: bypassing the label property because label set method now truncates to 255 characters
        self.obj.info.label = ' '.join('too long' for i in range(50))
        self.obj.info_modified = True
        try:
            self.obj.save()
        except models.DigitalObjectSaveFailure, f:
            profile_save_error = f
        self.assert_(isinstance(profile_save_error, models.DigitalObjectSaveFailure))
        self.assertEqual(profile_save_error.obj_pid, self.obj.pid,
            "save failure exception should include object pid %s, got %s" % (self.obj.pid, save_error.obj_pid))
        self.assertEqual(profile_save_error.failure, "object profile", )
        all_datastreams = ['TEXT', 'DC']
        self.assertEqual(all_datastreams, profile_save_error.to_be_saved)
        self.assertEqual(all_datastreams, profile_save_error.saved)
        self.assertEqual(all_datastreams, profile_save_error.cleaned)
        self.assertEqual([], profile_save_error.not_cleaned)
        self.assertTrue(profile_save_error.recovered)
        # confirm datastreams were reverted back to previous contents
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.text.id)
        self.assertEqual(TEXT_CONTENT, data)
        data, url = self.obj.api.getDatastreamDissemination(self.pid, self.obj.dc.id)
        self.assert_("<dc:description>This object has more data in it than a basic-object.</dc:description>" in data)

        # how to force an error that can't be backed out?

    def test_datastreams_list(self):
        self.assert_("DC" in self.obj.ds_list.keys())
        self.assert_(isinstance(self.obj.ds_list["DC"], ObjectDatastream))
        dc = self.obj.ds_list["DC"]
        self.assertEqual("DC", dc.dsid)
        self.assertEqual("Dublin Core", dc.label)
        self.assertEqual("text/xml", dc.mimeType)

        self.assert_("TEXT" in self.obj.ds_list.keys())
        text = self.obj.ds_list["TEXT"]
        self.assertEqual("text datastream", text.label)
        self.assertEqual("text/plain", text.mimeType)

    def test_history(self):
        self.assert_(isinstance(self.obj.history, list))
        self.assert_(isinstance(self.obj.history[0], datetime))
        self.assertEqual(self.ingest_time, self.obj.history[0])

    def test_methods(self):
        methods = self.obj.methods
        self.assert_('fedora-system:3' in methods)      # standard system sdef
        self.assert_('viewMethodIndex' in methods['fedora-system:3'])


    def test_has_model(self):
        cmodel_uri = "info:fedora/control:ContentType"
        # FIXME: checking when rels-ext datastream does not exist causes an error
        self.assertFalse(self.obj.has_model(cmodel_uri))
        self.obj.add_relationship(modelns.hasModel, cmodel_uri)
        self.assertTrue(self.obj.has_model(cmodel_uri))
        self.assertFalse(self.obj.has_model(self.obj.uri))

    def test_get_models(self):
        cmodel_uri = "info:fedora/control:ContentType"
        # FIXME: checking when rels-ext datastream does not exist causes an error
        self.assertEqual(self.obj.get_models(), [])
        self.obj.add_relationship(modelns.hasModel, cmodel_uri)
        self.assertEquals(self.obj.get_models(), [URIRef(cmodel_uri)])

    def test_has_requisite_content_models(self):
        # fixture has no content models
        # init fixture as generic object
        obj = models.DigitalObject(self.api, self.pid)
        # should have all required content models because there are none
        self.assertTrue(obj.has_requisite_content_models)

        # init fixture as test digital object with cmodels
        obj = MyDigitalObject(self.api, self.pid)
        # initially false since fixture has no cmodels
        self.assertFalse(obj.has_requisite_content_models)
        # add first cmodel
        obj.rels_ext.content.add((obj.uriref, modelns.hasModel,
                                       URIRef(MyDigitalObject.CONTENT_MODELS[0])))
        # should still be false since both are required
        self.assertFalse(obj.has_requisite_content_models)
        # add second cmodel
        obj.rels_ext.content.add((obj.uriref, modelns.hasModel,
                                       URIRef(MyDigitalObject.CONTENT_MODELS[1])))
        # now all cmodels should be present
        self.assertTrue(obj.has_requisite_content_models)
        # add an additional, extraneous cmodel
        obj.rels_ext.content.add((obj.uriref, modelns.hasModel,
                                       URIRef(SimpleDigitalObject.CONTENT_MODELS[0])))
        # should still be true
        self.assertTrue(obj.has_requisite_content_models)

    def test_add_relationships(self):
        # add relation to a resource, by digital object
        related = models.DigitalObject(self.api, "foo:123")
        added = self.obj.add_relationship(relsext.isMemberOf, related)
        self.assertTrue(added, "add relationship should return True on success, got %s" % added)
        rels_ext, url = self.obj.api.getDatastreamDissemination(self.pid, "RELS-EXT")
        self.assert_("isMemberOf" in rels_ext)
        self.assert_(related.uri in rels_ext) # should be full uri, not just pid

        # add relation to a resource, by string
        collection_uri = "info:fedora/foo:456"
        self.obj.add_relationship(relsext.isMemberOfCollection, collection_uri)
        rels_ext, url = self.obj.api.getDatastreamDissemination(self.pid, "RELS-EXT")
        self.assert_("isMemberOfCollection" in rels_ext)
        self.assert_(collection_uri in rels_ext)

        # add relation to a literal
        self.obj.add_relationship('info:fedora/example:owner', "testuser")
        rels_ext, url = self.obj.api.getDatastreamDissemination(self.pid, "RELS-EXT")
        self.assert_("owner" in rels_ext)
        self.assert_("testuser" in rels_ext)

        rels = self.obj.rels_ext.content
        # convert first added relationship to rdflib statement to check that it is in the rdf graph
        st = (self.obj.uriref, relsext.isMemberOf, related.uriref)
        self.assertTrue(st in rels)

    def test_registry(self):
        self.assert_('test_fedora.test_models.MyDigitalObject' in
                     models.DigitalObject.defined_types)

    def test_index_data(self):
        indexdata = self.obj.index_data()
        # check that top-level object properties are included in index data
        # (implicitly checking types)
        self.assertEqual(self.obj.pid, indexdata['pid'])
        self.assertEqual(self.obj.owners, indexdata['owner'])
        self.assertEqual(self.obj.label, indexdata['label'])
        self.assertEqual(self.obj.modified.isoformat(), indexdata['last_modified'])
        self.assertEqual(self.obj.created.isoformat(), indexdata['created'])
        self.assertEqual(self.obj.state, indexdata['state'])
        for cm in self.obj.get_models():
            self.assert_(str(cm) in indexdata['content_model'])
            
        # descriptive data included in index data
        self.assert_(self.obj.dc.content.title in indexdata['title'])
        self.assert_(self.obj.dc.content.description in indexdata['description'])

        self.assertEqual(['TEXT', 'DC'], indexdata['dsids'])

    def test_index_data_relations(self):
        # add a few rels-ext relations to test
        partof = 'something bigger'
        self.obj.rels_ext.content.add((self.obj.uriref, relsext.isPartOf, URIRef(partof)))
        member1 = 'foo'
        member2 = 'bar'
        self.obj.rels_ext.content.add((self.obj.uriref, relsext.hasMember, URIRef(member1)))
        self.obj.rels_ext.content.add((self.obj.uriref, relsext.hasMember, URIRef(member2)))
        indexdata = self.obj.index_data_relations()
        self.assertEqual([partof], indexdata['isPartOf'])
        self.assert_(member1 in indexdata['hasMember'])
        self.assert_(member2 in indexdata['hasMember'])
        # rels-ext data included in main index data
        indexdata = self.obj.index_data()
        self.assert_('isPartOf' in indexdata)
        self.assert_('hasMember' in indexdata)

    def test_get_object(self):
        obj = MyDigitalObject(self.api)
        otherobj = obj.get_object(self.pid)

        self.assert_(isinstance(otherobj, MyDigitalObject),
            'if type is not specified, get_object should return current type')
        self.assertEqual(self.api, otherobj.api,
            'get_object should pass existing api connection')
        
        otherobj = obj.get_object(self.pid, type=SimpleDigitalObject)
        self.assert_(isinstance(otherobj, SimpleDigitalObject),
            'get_object should object with requested type')
        


class TestContentModel(FedoraTestCase):

    def tearDown(self):
        super(TestContentModel, self).tearDown()
        cmodels = list(MyDigitalObject.CONTENT_MODELS)
        cmodels.extend(SimpleDigitalObject.CONTENT_MODELS)
        for pid in cmodels:
            try:
                self.repo.purge_object(pid)
            except RequestFailed as rf:
                logger.warn('Error purging %s: %s' % (pid, rf))

    def test_for_class(self):
        CMODEL_URI = models.ContentModel.CONTENT_MODELS[0]

        # NOTE: these tests can fail if a content model with the same
        # URI (but not the same datastreams) actually exists in Fedora
        
        # first: create a cmodel for SimpleDigitalObject, the simple case
        cmodel = models.ContentModel.for_class(SimpleDigitalObject, self.repo)
        self.append_test_pid(cmodel.pid)
        expect_uri = SimpleDigitalObject.CONTENT_MODELS[0]
        self.assertEqual(cmodel.uri, expect_uri)
        self.assertTrue(cmodel.has_model(CMODEL_URI))

        dscm = cmodel.ds_composite_model.content
        typemodel = dscm.get_type_model('TEXT')
        self.assertEqual(typemodel.mimetype, 'text/plain')

        typemodel = dscm.get_type_model('EXTRADC')
        self.assertEqual(typemodel.mimetype, 'text/xml')

        # try ContentModel itself. Content model objects have the "content
        # model" content model. That content model should already be in
        # every repo, so for_class shouldn't need to make anything.
        cmodel = models.ContentModel.for_class(models.ContentModel, self.repo)
        expect_uri = models.ContentModel.CONTENT_MODELS[0]
        self.assertEqual(cmodel.uri, expect_uri)
        self.assertTrue(cmodel.has_model(CMODEL_URI))

        dscm = cmodel.ds_composite_model.content
        typemodel = dscm.get_type_model('DS-COMPOSITE-MODEL')
        self.assertEqual(typemodel.mimetype, 'text/xml')
        self.assertEqual(typemodel.format_uri, 'info:fedora/fedora-system:FedoraDSCompositeModel-1.0')

        # try MyDigitalObject. this should fail, as MyDigitalObject has two
        # CONTENT_MODELS: we support only one
        self.assertRaises(ValueError, models.ContentModel.for_class,
                          MyDigitalObject, self.repo)


# using DC namespace to test RDF literal values
DCNS = Namespace(URIRef('http://purl.org/dc/elements/1.1/'))        

class RelatorObject(MyDigitalObject):
    # related object
    parent = models.Relation(relsext.isMemberOfCollection, type=SimpleDigitalObject)
    # literal
    dctitle = models.Relation(DCNS.title)
    # literal with explicit type and namespace prefix
    dcid = models.Relation(DCNS.identifier, ns_prefix={'dcns': DCNS}, rdf_type=XSD.int)


class ReverseRelator(MyDigitalObject):
    member = models.ReverseRelation(relsext.isMemberOfCollection, type=RelatorObject)
    members = models.ReverseRelation(relsext.isMemberOfCollection,
                                     type=RelatorObject, multiple=True)

class TestRelation(FedoraTestCase):
    fixtures = ['object-with-pid.foxml']
    
    def setUp(self):
        super(TestRelation, self).setUp()
        #self.pid = self.fedora_fixtures_ingested[-1] # get the pid for the last object
        self.obj = RelatorObject(self.api)

    def test_object_relation(self):
        # get - not yet set
        self.assertEqual(None, self.obj.parent)
        
        # set via descriptor
        newobj = models.DigitalObject(self.api)
        newobj.pid = 'foo:2'	# test pid for convenience/distinguish temp pids
        self.obj.parent = newobj
        self.assert_((self.obj.uriref, relsext.isMemberOfCollection, newobj.uriref)
            in self.obj.rels_ext.content,
            'isMemberOfCollection should be set in RELS-EXT after updating via descriptor')
        # access via descriptor
        self.assertEqual(newobj.pid, self.obj.parent.pid)
        self.assert_(isinstance(self.obj.parent, SimpleDigitalObject),
                     'Relation descriptor returns configured type of DigitalObject')
        # set existing property
        otherobj = models.DigitalObject(self.api)
        otherobj.pid = 'bar:none'
        self.obj.parent = otherobj
        self.assert_((self.obj.uriref, relsext.isMemberOfCollection, otherobj.uriref)
            in self.obj.rels_ext.content,
            'isMemberOfCollection should be updated in RELS-EXT after update')
        self.assert_((self.obj.uriref, relsext.isMemberOfCollection, newobj.uriref)
            not in self.obj.rels_ext.content,
            'previous isMemberOfCollection value should not be in RELS-EXT after update')
        
        # delete
        del self.obj.parent
        self.assertEqual(None, self.obj.rels_ext.content.value(subject=self.obj.uriref,
                                                               predicate=relsext.isMemberOfCollection),
                         'isMemberOfCollection should not be set in rels-ext after delete')
        
    def test_literal_relation(self):
        # get - not set
        self.assertEqual(None, self.obj.dcid)
        self.assertEqual(None, self.obj.dctitle)
       
        # set via descriptor
        # - integer, with type specified
        self.obj.dcid = 1234
        self.assert_((self.obj.uriref, DCNS.identifier, Literal(1234, datatype=XSD.int))
            in self.obj.rels_ext.content,
            'literal value should be set in RELS-EXT after updating via descriptor')
        # check namespace prefix
        self.assert_('dcns:identifier' in self.obj.rels_ext.content.serialize(),
            'configured namespace prefix should be used for serialization')
        # check type
        self.assert_('XMLSchema#int' in self.obj.rels_ext.content.serialize(),
            'configured RDF type should be used for serialization')
        # - simpler case
        self.obj.dctitle = 'foo'
        self.assert_((self.obj.uriref, DCNS.title, Literal('foo'))
            in self.obj.rels_ext.content,
            'literal value should be set in RELS-EXT after updating via descriptor')
        self.assertEqual('foo', self.obj.dctitle)
        

        # get
        self.assertEqual(1234, self.obj.dcid)

        # update
        self.obj.dcid = 987
        self.assertEqual(987, self.obj.dcid)

        # delete
        del self.obj.dcid
        self.assertEqual(None, self.obj.rels_ext.content.value(subject=self.obj.uriref,
                                                               predicate=DCNS.identifier),
                         'dc:identifier should not be set in rels-ext after delete')
        
    def test_reverse_relation(self):
        rev = ReverseRelator(self.api, 'foo:1')
        # add a relation to the object and save so we can query risearch
        self.obj.parent = rev
        self.obj.save()
        self.fedora_fixtures_ingested.append(self.obj.pid) # save pid for cleanup in tearDown
        self.assertEqual(rev.member.pid, self.obj.pid,
            'ReverseRelation returns correct object based on risearch query')
        self.assert_(isinstance(rev.member, RelatorObject),
            'ReverseRelation returns correct object type')

        self.assert_(isinstance(rev.members, list),
            'ReverseRelation returns list when multiple=True')
        self.assertEqual(rev.members[0].pid, self.obj.pid,
            'ReverseRelation list includes correct item')
        self.assert_(isinstance(rev.members[0], RelatorObject),
            'ReverseRelation list items initialized as correct object type')
        
        
       



if __name__ == '__main__':
    main()

