import hashlib
import logging
from lxml import etree
from mock import Mock, patch
import os
import requests
import unittest
from urllib import url2pathname


from eulfedora.models import DigitalObject
from eulfedora.server import Repository
from eulfedora.syncutil import ArchiveExport
from eulfedora.util import md5sum
from test.test_fedora.base import FIXTURE_ROOT


logger = logging.getLogger(__name__)


class ArchiveExportTest(unittest.TestCase):

    sync1_export = os.path.join(FIXTURE_ROOT, 'synctest1-export.xml')
    sync2_export = os.path.join(FIXTURE_ROOT, 'synctest2-export.xml')

    def setUp(self):
        # todo: use mocks?
        self.repo = Mock(spec=Repository)
        self.obj = Mock() #spec=DigitalObject)
        self.archex = ArchiveExport(self.obj, self.repo)

        # set up a request session that can load file uris, so
        # fixtures can be used as export data
        self.session = requests.session()
        self.session.mount('file://', LocalFileAdapter())


    def test_has_binary_content(self):
        # sample archival export content with open binary content tag
        self.assertTrue(self.archex.has_binary_content('''</foxml:datastream>
<foxml:datastream ID="MODS" STATE="A" CONTROL_GROUP="M" VERSIONABLE="true">
<foxml:datastreamVersion ID="MODS.0" LABEL="MODS Metadata" CREATED="2015-11-12T15:07:21.130Z" MIMETYPE="text/xml" FORMAT_URI="http://w
ww.loc.gov/mods/v3" SIZE="345">
<foxml:contentDigest TYPE="MD5" DIGEST="651fb5d5b4437867a6664c767706aeae"/>
<foxml:binaryContent>
              PG1vZHM6bW9kcyB4bWxuczptb2RzPSJodHRwOi8vd3d3LmxvYy5nb3YvbW9kcy92MyI+PG1vZHM6dGl0
              bGVJbmZvPjxtb2RzOnRpdGxlPnE0bnM0LndhdjwvbW9kczp0aXRsZT48L21vZHM6dGl0bGVJbmZvPjxt
              b2RzOnR5cGVPZlJlc291cmNlP'''))

        # sample archival export content with close binary tag
        self.assertTrue(self.archex.has_binary_content('''</foxml:datastream>
          aW9uPjxkdDptZWFzdXJlIHR5cGU9InRpbWUiIHVuaXQ9InNlY29uZHMiIGFzcGVjdD0iZHVyYXRpb24g
              b2YgcGxheWluZyB0aW1lIj42MDc8L2R0Om1lYXN1cmU+PC9kdDpkdXJhdGlvbj48L2R0OmRpZ2l0YWx0
              ZWNoPg==
</foxml:binaryContent>
</foxml:datastreamVersion>
</foxml:datastream>
<foxml:datastream ID="DC" STATE="A" CONTROL_GROUP="M" VERSIONABLE="true">
<foxml:datastreamVersion ID="DC.0" LABEL="Dublin Core" CREATED="2015-11-12T15:07:21.130Z" MIMETYPE="text/xml" FORMAT_URI="http://www.openarchives.org/OAI/2.0/oai_dc/" SIZE="409">'''))

        # sample with multiple close and open binary tags
        self.assertTrue(self.archex.has_binary_content('''ZWNoPg==
</foxml:binaryContent>
</foxml:datastreamVersion>
</foxml:datastream>
<foxml:datastream ID="DC" STATE="A" CONTROL_GROUP="M" VERSIONABLE="true">
<foxml:datastreamVersion ID="DC.0" LABEL="Dublin Core" CREATED="2015-11-12T15:07:21.130Z" MIMETYPE="text/xml" FORMAT_URI="http://www.o
penarchives.org/OAI/2.0/oai_dc/" SIZE="409">
<foxml:contentDigest TYPE="MD5" DIGEST="49b8129d6ba695a9fb73167900519d90"/>
<foxml:binaryContent>
              PG9haV9kYzpkYyB4bWxuczpvYWlfZGM9Imh0dHA6Ly93d3cub3BlbmFyY2hpdmVzLm9yZy9PQUkvMi4w
              L29haV9kYy8iCnhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIKeG1sbnM6
              eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIKeHNpOnNjaGVtYUxv
              Y2F0aW9uPSJodHRwOi8vd3d3Lm9wZW5hcmNoaXZlcy5vcmcvT0FJLzIuMC9vYWlfZGMvIGh0dHA6Ly93
              d3cub3BlbmFyY2hpdmVzLm9yZy9PQUkvMi4wL29haV9kYy54c2QiPgogIDxkYzp0aXRsZT5xNG5zNC53
              YXY8L2RjOnRpdGxlPgogIDxkYzp0eXBlPnNvdW5kIHJlY29yZGluZzwvZGM6dHlwZT4KICA8ZGM6aWRl
              bnRpZmllcj5lbW9yeTpweHBybjwvZGM6aWRlbnRpZmllcj4KPC9vYWlfZGM6ZGM+Cg==
</foxml:binaryContent>
</foxml:datastreamVersion>'''))

        # sample archival export content without binary tags
        self.assertFalse(self.archex.has_binary_content('''<foxml:digitalObject VERSION="1.1" PID="emory:pxprn"
xmlns:foxml="info:fedora/fedora-system:def/foxml#"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="info:fedora/fedora-system:def/foxml# http://www.fedora.info/definitions/1/0/foxml1-1.xsd">
<foxml:objectProperties>
<foxml:property NAME="info:fedora/fedora-system:def/model#state" VALUE="Active"/>
<foxml:property NAME="info:fedora/fedora-system:def/model#label" VALUE="q4ns4.wav"/>
<foxml:property NAME="info:fedora/fedora-system:def/model#ownerId" VALUE="thekeep-project"/>
<foxml:property NAME="info:fedora/fedora-system:def/model#createdDate" VALUE="2015-11-12T15:07:21.130Z"/>
<foxml:property NAME="info:fedora/fedora-system:def/view#lastModifiedDate" VALUE="2016-01-14T06:30:12.295Z"/>
</foxml:objectProperties>'''))

    def test_get_datastream_info(self):
        dsinfo = self.archex.get_datastream_info('''<foxml:datastreamVersion ID="DC.2" LABEL="Dublin Core" CREATED="2012-10-11T14:13:03.658Z" MIMETYPE="text/xml" FORMAT_URI="http://www.openarchives.org/OAI/2.0/oai_dc/" SIZE="771">
<foxml:contentDigest TYPE="MD5" DIGEST="f53aec07f2607f536bac7ee03dbbfe7c"/>''')
        self.assertEqual('DC.2', dsinfo['id'])
        self.assertEqual('text/xml', dsinfo['mimetype'])
        self.assertEqual('771', dsinfo['size'])
        self.assertEqual('MD5', dsinfo['type'])
        self.assertEqual('f53aec07f2607f536bac7ee03dbbfe7c', dsinfo['digest'])

        # datastream info split across chunks
        self.archex.end_of_last_chunk = '''<foxml:datastreamVersion ID="DC.2" LABEL="Dublin Core" CREATED="2012-10-11T14:13:03.658Z" MIMETYPE="te'''
        dsinfo = self.archex.get_datastream_info('''xt/xml" FORMAT_URI="http://www.openarchives.org/OAI/2.0/oai_dc/" SIZE="771">
<foxml:contentDigest TYPE="MD5" DIGEST="f53aec07f2607f536bac7ee03dbbfe7c"/>''')
        self.assertEqual('DC.2', dsinfo['id'])
        self.assertEqual('text/xml', dsinfo['mimetype'])
        self.assertEqual('f53aec07f2607f536bac7ee03dbbfe7c', dsinfo['digest'])


    def test_object_data(self):
        # mock api to read export data from a local fixture filie
        response = self.session.get('file://%s' % self.sync1_export)
        mockapi = Mock()
        def mock_upload(data, size):
            list(data)  # consume the generator so datastream processing happens
            return 'uploaded://1'

        mockapi.upload = mock_upload
        mockapi.export.return_value = response
        self.obj.api = self.repo.api = mockapi
        data = self.archex.object_data()
        foxml = data.getvalue()
        with open('/tmp/foxml-sync1.xml', 'w') as testfile:
            testfile.write(foxml)

        self.assert_(etree.XML(foxml) is not None,
            'object data should be valid xml')
        self.assert_('foxml:binaryContent' not in foxml,
            'object data for ingest should not include binaryContent tags')
        self.assert_('<foxml:contentLocation REF="uploaded://1" TYPE="URL"/>' in foxml,
            'object data for ingest should include upload id as content location')

        # other tests?

        # set read block size artificially low to test chunked handling
        self.archex = ArchiveExport(self.obj, self.repo)
        self.archex.read_block_size = 1024
        data = self.archex.object_data()
        foxml = data.getvalue()

        self.assert_(etree.XML(foxml) is not None,
            'object data should be valid xml')
        self.assert_('foxml:binaryContent' not in foxml,
            'object data for ingest should not include binaryContent tags')
        self.assert_('<foxml:contentLocation REF="uploaded://1" TYPE="URL"/>' in foxml,
            'object data for ingest should include upload id as content location')

        # test with second fixture - multiple small encoded datastreams
        self.archex = ArchiveExport(self.obj, self.repo)
        self.archex.read_block_size = 1024
        response = self.session.get('file://%s' % self.sync2_export)
        mockapi.export.return_value = response
        data = self.archex.object_data()
        foxml = data.getvalue()

        self.assert_(etree.XML(foxml) is not None,
            'object data should be valid xml')
        self.assert_('foxml:binaryContent' not in foxml,
            'object data for ingest should not include binaryContent tags')
        self.assert_('<foxml:contentLocation REF="uploaded://1" TYPE="URL"/>' in foxml,
            'object data for ingest should include upload id as content location')

    def test_encoded_datastream(self):
        # data content within a single chunk of data
        mockapi = Mock()
        mockapi.export.return_value = self.session.get('file://%s' % self.sync1_export)
        mockapi.upload.return_value = 'uploaded://1'
        self.obj.api = self.repo.api = mockapi

        section = self.archex.get_next_section()
        # get binary datastream info from first section
        dsinfo = self.archex.get_datastream_info(section)
        # fixture only has one binary content block
        # get binarycontent tag out of the way
        self.archex.get_next_section()
        # next section will be file contents
        self.archex.within_file = True
        dscontent = ''.join(self.archex.encoded_datastream())
        # check decoded size and MD5 match data from fixture
        self.assertEqual(int(dsinfo['size']), len(dscontent))
        self.assertEqual(dsinfo['digest'], md5sum(dscontent))

        # data content across multiple chunks
        mockapi.export.return_value = self.session.get('file://%s' % self.sync1_export)
        self.obj.api = self.repo.api = mockapi
        # set read block size artificially low to ensure
        # datastream content is spread across multiple chunks
        self.archex.read_block_size = 1024

        finished = False
        # iterate through the data, similar to object_data method,
        # but only handle binary content
        while not finished:
            try:
                section = self.archex.get_next_section()
            except StopIteration:
                finished = True

            # find the section with starting binary content
            if section == '<foxml:binaryContent>':
                # then decode the subsequent content
                self.archex.within_file = True
                dscontent = ''.join(self.archex.encoded_datastream())

                self.assertEqual(int(dsinfo['size']), len(dscontent))
                self.assertEqual(dsinfo['digest'], md5sum(dscontent))

                # stop processing
                finished = True



# requests file uri adapter, thanks to
# http://stackoverflow.com/questions/10123929/python-requests-fetch-a-file-from-a-local-url
class LocalFileAdapter(requests.adapters.BaseAdapter):
    """Protocol Adapter to allow Requests to GET file:// URLs

    @todo: Properly handle non-empty hostname portions.
    """

    @staticmethod
    def _chkpath(method, path):
        """Return an HTTP status for the given filesystem path."""
        if method.lower() in ('put', 'delete'):
            return 501, "Not Implemented"  # TODO
        elif method.lower() not in ('get', 'head'):
            return 405, "Method Not Allowed"
        elif os.path.isdir(path):
            return 400, "Path Not A File"
        elif not os.path.isfile(path):
            return 404, "File Not Found"
        elif not os.access(path, os.R_OK):
            return 403, "Access Denied"
        else:
            return 200, "OK"

    def send(self, req, **kwargs):  # pylint: disable=unused-argument
        """Return the file specified by the given request

        @type req: C{PreparedRequest}
        @todo: Should I bother filling `response.headers` and processing
               If-Modified-Since and friends using `os.stat`?
        """
        path = os.path.normcase(os.path.normpath(url2pathname(req.path_url)))
        response = requests.Response()

        response.status_code, response.reason = self._chkpath(req.method, path)
        if response.status_code == 200 and req.method.lower() != 'head':
            try:
                response.raw = open(path, 'rb')
            except (OSError, IOError), err:
                response.status_code = 500
                response.reason = str(err)

        if isinstance(req.url, bytes):
            response.url = req.url.decode('utf-8')
        else:
            response.url = req.url

        response.request = req
        response.connection = self

        return response

    def close(self):
        pass

