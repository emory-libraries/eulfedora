# file eulfedora/xml.py
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

from __future__ import unicode_literals
from eulxml import xmlmap
from eulxml.xmlmap.fields import Field, SingleNodeManager, NodeMapper, \
                                 DateTimeField

from eulfedora.util import datetime_to_fedoratime, fedoratime_to_datetime

class FedoraDateMapper(xmlmap.fields.DateTimeMapper):
    def to_python(self, node):
        rep = self.XPATH(node)
        return fedoratime_to_datetime(rep)

    def to_xml(self, dt):
        return datetime_to_fedoratime(dt)

class FedoraDateField(xmlmap.fields.Field):
    """Map an XPath expression to a single Python `datetime.datetime`.
    Assumes date-time format in use by Fedora, e.g. 2010-05-20T18:42:52.766Z
    """
    def __init__(self, xpath):
        super(FedoraDateField, self).__init__(xpath,
                manager = xmlmap.fields.SingleNodeManager(),
                mapper = FedoraDateMapper())

class FedoraDateListField(xmlmap.fields.Field):
    """Map an XPath expression to a list of Python `datetime.datetime`.
    Assumes date-time format in use by Fedora, e.g. 2010-05-20T18:42:52.766Z.
    If the XPath expression evaluates to an empty NodeList, evaluates to
    an empty list."""

    def __init__(self, xpath):
        super(FedoraDateListField, self).__init__(xpath,
                manager = xmlmap.fields.NodeListManager(),
                mapper = FedoraDateMapper())


# xml objects to wrap around xml returns from fedora

FEDORA_MANAGE_NS = 'http://www.fedora.info/definitions/1/0/management/'
FEDORA_ACCESS_NS = 'http://www.fedora.info/definitions/1/0/access/'
FEDORA_DATASTREAM_NS = 'info:fedora/fedora-system:def/dsCompositeModel#'
FEDORA_TYPES_NS = 'http://www.fedora.info/definitions/1/0/types/'
FEDORA_AUDIT_NS = 'info:fedora/fedora-system:def/audit#'


class _FedoraBase(xmlmap.XmlObject):
    '''Common Fedora REST API namespace declarations.'''
    ROOT_NAMESPACES = {
        'm' : FEDORA_MANAGE_NS,
        'a' : FEDORA_ACCESS_NS,
        'ds': FEDORA_DATASTREAM_NS,
        't': FEDORA_TYPES_NS,
        'audit': FEDORA_AUDIT_NS
    }

class ObjectDatastream(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for a single datastream as returned
        by :meth:`REST_API.listDatastreams` """
    ROOT_NAME = 'datastream'
    dsid = xmlmap.StringField('@dsid')
    "datastream id - `@dsid`"
    label = xmlmap.StringField('@label')
    "datastream label - `@label`"
    mimeType = xmlmap.StringField('@mimeType')
    "datastream mime type - `@mimeType`"

class ObjectDatastreams(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for the list of a single object's
        datastreams, as returned by  :meth:`REST_API.listDatastreams`"""
    # listDatastreams result default namespace is fedora access
    ROOT_NAME = 'objectDatastreams'
    pid = xmlmap.StringField('@pid')
    "object pid - `@pid`"
    datastreams = xmlmap.NodeListField('a:datastream', ObjectDatastream)
    "list of :class:`ObjectDatastream`"

class ObjectProfile(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for object profile information
        returned by :meth:`REST_API.getObjectProfile`."""
    # objectProfile result default namespace is fedora access
    ROOT_NAME = 'objectProfile'
    label = xmlmap.StringField('a:objLabel')
    "object label"
    owner = xmlmap.StringField('a:objOwnerId')
    "object owner"
    created = FedoraDateField('a:objCreateDate')
    "date the object was created"
    modified = FedoraDateField('a:objLastModDate')
    "date the object was last modified"
    # do we care about these? probably not useful in this context...
    # - disseminator index view url
    # - object item index view url
    state = xmlmap.StringField('a:objState')
    "object state (A/I/D - Active, Inactive, Deleted)"

class ObjectHistory(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for object history information
        returned by :meth:`REST_API.getObjectHistory`."""
    # objectHistory result default namespace is fedora access
    ROOT_NAME = 'fedoraObjectHistory'
    pid = xmlmap.StringField('@pid')
    changed = FedoraDateListField('a:objectChangeDate')

class ObjectMethodService(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for object method services; included
    in :class:`ObjectMethods` for data returned by  :meth:`REST_API.listMethods`."""
    # default namespace is fedora access
    ROOT_NAME = 'sDef'
    pid = xmlmap.StringField('@pid')
    methods = xmlmap.StringListField('a:method/@name')

class ObjectMethods(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for object method information
    returned by  :meth:`REST_API.listMethods`."""
    # default namespace is fedora access
    ROOT_NAME = 'objectMethods'
    service_definitions = xmlmap.NodeListField('a:sDef', ObjectMethodService)

class DatastreamProfile(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for datastream profile information
    returned by  :meth:`REST_API.getDatastream`."""
    # default namespace is fedora manage
    ROOT_NAME = 'datastreamProfile'
    label = xmlmap.StringField('m:dsLabel')
    "datastream label"
    version_id = xmlmap.StringField('m:dsVersionID')
    "current datastream version id"
    created = FedoraDateField('m:dsCreateDate')
    "date the datastream was created"
    state = xmlmap.StringField('m:dsState')
    "datastream state (A/I/D - Active, Inactive, Deleted)"
    mimetype = xmlmap.StringField('m:dsMIME')
    "datastream mimetype"
    format = xmlmap.StringField('m:dsFormatURI')
    "format URI for the datastream, if any"
    control_group = xmlmap.StringField('m:dsControlGroup')
    "datastream control group (inline XML, Managed, etc)"
    size = xmlmap.IntegerField('m:dsSize')    # not reliable for managed datastreams as of Fedora 3.3
    "integer; size of the datastream content"
    versionable = xmlmap.SimpleBooleanField('m:dsVersionable', 'true', 'false')
    "boolean; indicates whether or not the datastream is currently being versioned"
    # infoType ?
    # location ?
    checksum = xmlmap.StringField('m:dsChecksum')
    "checksum for current datastream contents"
    checksum_type = xmlmap.StringField('m:dsChecksumType')
    "type of checksum"
    checksum_valid = xmlmap.SimpleBooleanField('m:dsChecksumValid', 'true', 'false')
    '''Boolean flag indicating if the current checksum is valid.  Only
    present when profile is accessed via :meth:`REST_API.compareDatastreamChecksum`'''

class NewPids(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for a list of pids as returned by
    :meth:`REST_API.getNextPID`."""
    # NOTE: default namespace as of should be manage, but the
    # namespace was missing until Fedora 3.5.  Match with or without a
    # namespace, to support Fedora 3.5 as well as older versions.
    pids = xmlmap.StringListField('pid|m:pid')


class RepositoryDescriptionPid(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for PID section of :class:`RepositoryDescription`"""
    # default namespace is fedora access
    namespace = xmlmap.StringField('a:PID-namespaceIdentifier')
    "PID namespace"
    delimiter = xmlmap.StringField('a:PID-delimiter')
    "PID delimiter"
    sample = xmlmap.StringField('a:PID-sample')
    "sample PID"
    retain_pids = xmlmap.StringField('a:retainPID')
    "list of pid namespaces configured to be retained"

class RepositoryDescriptionOAI(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for OAI section of :class:`RepositoryDescription`"""
    # default namespace is fedora access
    namespace = xmlmap.StringField('a:OAI-namespaceIdentifier')
    "OAI namespace"
    delimiter = xmlmap.StringField('a:OAI-delimiter')
    "OAI delimiter"
    sample = xmlmap.StringField('a:OAI-sample')
    "sample OAI id"

class RepositoryDescription(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for a repository description as returned
        by :meth:`API_A_LITE.describeRepository` """
    # default namespace is fedora access
    name = xmlmap.StringField('a:repositoryName')
    "repository name"
    base_url = xmlmap.StringField('a:repositoryBaseURL')
    "base url"
    version = xmlmap.StringField('a:repositoryVersion')
    "version of Fedora being run"
    pid_info = xmlmap.NodeField('a:repositoryPID', RepositoryDescriptionPid)
    ":class:`RepositoryDescriptionPid` - configuration info for pids"
    oai_info = xmlmap.NodeField('a:repositoryPID', RepositoryDescriptionOAI)
    ":class:`RepositoryDescriptionOAI` - configuration info for OAI"
    search_url = xmlmap.StringField('a:sampleSearch-URL')
    "sample search url"
    access_url = xmlmap.StringField('a:sampleAccess-URL')
    "sample access url"
    oai_url = xmlmap.StringField('a:sampleOAI-URL')
    "sample OAI url"
    admin_email = xmlmap.StringListField("a:adminEmail")
    "administrator emails"

class SearchResult(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for a single entry in the results
        returned by :meth:`REST_API.findObjects`"""
    # default namespace is fedora types
    ROOT_NAME = 'objectFields'
    pid = xmlmap.StringField('t:pid')
    "pid"

class SearchResults(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for the results returned by
        :meth:`REST_API.findObjects`"""
    # default namespace is fedora types
    ROOT_NAME = 'result'
    session_token = xmlmap.StringField('t:listSession/t:token')
    "session token"
    cursor = xmlmap.IntegerField('t:listSession/t:cursor')
    "session cursor"
    expiration_date = DateTimeField('t:listSession/t:expirationDate')
    "session experation date"
    results = xmlmap.NodeListField('t:resultList/t:objectFields', SearchResult)
    "search results - list of :class:`SearchResult`"


class DatastreamHistory(_FedoraBase):
    """:class:`~eulxml.xmlmap.XmlObject` for datastream history
    information returned by :meth:`REST_API.getDatastreamHistory`."""
    # default namespace is fedora manage
    ROOT_NAME = 'datastreamHistory'
    pid = xmlmap.StringField('@pid')
    "pid"
    dsid = xmlmap.StringField('@dsID')
    "datastream id"
    versions = xmlmap.NodeListField('m:datastreamProfile', DatastreamProfile)
    'list of :class:`DatastreamProfile` objects for each version'


DS_NAMESPACES = {'ds': FEDORA_DATASTREAM_NS }

class DsTypeModel(xmlmap.XmlObject):
    ROOT_NAMESPACES = DS_NAMESPACES

    id = xmlmap.StringField('@ID')
    mimetype = xmlmap.StringField('ds:form/@MIME')
    format_uri = xmlmap.StringField('ds:form/@FORMAT_URI')


class DsCompositeModel(xmlmap.XmlObject):
    """:class:`~eulxml.xmlmap.XmlObject` for a
    :class:`~eulfedora.models.ContentModel`'s DS-COMPOSITE-MODEL
    datastream"""

    ROOT_NAME = 'dsCompositeModel'
    ROOT_NS = FEDORA_DATASTREAM_NS
    ROOT_NAMESPACES = DS_NAMESPACES

    # TODO: this feels like it could be generalized into a dict-like field
    # class.
    TYPE_MODEL_XPATH = 'ds:dsTypeModel[@ID=$dsid]'
    def get_type_model(self, dsid, create=False):
            field = Field(self.TYPE_MODEL_XPATH,
                        manager=SingleNodeManager(instantiate_on_get=create),
                        mapper=NodeMapper(DsTypeModel))
            context = { 'namespaces': DS_NAMESPACES,
                        'dsid': dsid }
            return field.get_for_node(self.node, context)


class AuditTrailRecord(_FedoraBase):
    ''':class:`~eulxml.xmlmap.XmlObject` for a single audit entry in
    an :class:`AuditTrail`.
    '''
    ROOT_NAME = 'record'
    ROOT_NS = FEDORA_AUDIT_NS

    id = xmlmap.StringField('@ID')
    'id for this audit trail record'
    process_type = xmlmap.StringField('audit:process/@type')
    'type of modification, e.g. `Fedora API-M`'
    action = xmlmap.StringField('audit:action')
    'the particular action taken, e.g. `addDatastream`'
    component = xmlmap.StringField('audit:componentID')
    'the component that was modified, e.g. a datastream ID such as `DC` or `RELS-EXT`'
    user = xmlmap.StringField('audit:responsibility')
    'the user or account responsible for the change (e.g., `fedoraAdmin`)'
    date = FedoraDateField('audit:date')
    'date the change was made, as :class:`datetime.datetime`'
    message = xmlmap.StringField('audit:justification')
    'justification for the change, if any (i.e., log message passed to save method)'

class AuditTrail(_FedoraBase):
    ''':class:`~eulxml.xmlmap.XmlObject` for the Fedora built-in audit trail
    that is automatically populated from any modifications made to an object.
    '''
    records = xmlmap.NodeListField('audit:record', AuditTrailRecord)
    'list of :class:`AuditTrailRecord` entries'


class FoxmlContentDigest(_FedoraBase):
    'Content digest, as stored in full foxml (e.g. object export)'
    #: digest type, e.g. MD5
    type = xmlmap.StringField('@TYPE')
    #: digest value
    digest = xmlmap.StringField('@DIGEST')


class FoxmlDatastreamVersion(_FedoraBase):
    'Foxml datastream version in full foxml, e.g. object export'
    #: datastream version id
    id = xmlmap.StringField('@ID')
    #: mimetype
    mimetype = xmlmap.StringField('@MIMETYPE')
    #: content digest
    content_digest = xmlmap.NodeListField('foxml:contentDigest',
        FoxmlContentDigest)

class FoxmlDatastream(_FedoraBase):
    'Foxml datastream in full foxml, e.g. object export'
    #: datastream id
    id = xmlmap.StringField('@ID')
    #: list of versions
    versions = xmlmap.NodeListField('foxml:datastreamVersion',
        FoxmlDatastreamVersion)

class FoxmlDigitalObject(_FedoraBase):
    '''Minimal :class:`~eulxml.xmlmap.XmlObject` for Foxml
    DigitalObject as returned by :meth:`REST_API.getObjectXML`, to
    provide access to the Fedora audit trail.
    '''
    audit_trail = xmlmap.NodeField('foxml:datastream[@ID="AUDIT"]/foxml:datastreamVersion/foxml:xmlContent/audit:auditTrail', AuditTrail)
    'Fedora audit trail, as instance of :class:`AuditTrail`'
    datastreams = xmlmap.NodeListField('foxml:datastream', FoxmlDatastream)
