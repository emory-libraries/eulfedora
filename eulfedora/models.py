# file eulfedora/models.py
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

import cStringIO
import hashlib
import logging

from rdflib import URIRef, Graph as RdfGraph, Literal

from lxml import etree
from lxml.builder import ElementMaker

from eulxml import xmlmap
from eulfedora.api import ResourceIndex
from eulfedora.rdfns import model as modelns, relsext as relsextns, fedora_rels
from eulfedora.util import parse_xml_object, parse_rdf, RequestFailed, datetime_to_fedoratime
from eulfedora.xml import ObjectDatastreams, ObjectProfile, DatastreamProfile, \
    NewPids, ObjectHistory, ObjectMethods, DsCompositeModel
from eulxml.xmlmap.dc import DublinCore

logger = logging.getLogger(__name__)

class DatastreamObject(object):
    """Object to ease accessing and updating a datastream belonging to a Fedora
    object.  Handles datastream content as well as datastream profile information.
    Content and datastream info are only pulled from Fedora when content and info
    fields are accessed.

    Intended to be used with :class:`DigitalObject` and intialized
    via :class:`Datastream`.  

    Initialization parameters:
        :param obj: the :class:`DigitalObject` that this datastream belongs to.
        :param id: datastream id
        :param label: default datastream label
        :param mimetype: default datastream mimetype
        :param versionable: default configuration for datastream versioning
        :param state: default configuration for datastream state
        :param format: default configuration for datastream format URI
        :param checksum: default configuration for datastream checksum
        :param checksum_type: default configuration for datastream checksum type 
    """
    default_mimetype = "application/octet-stream"

    ds_location = None
    '''Datastream content location: set this attribute to a URI that
    Fedora can resolve (e.g., http:// or file://) in order to add or
    update datastream content from a known, accessible location,
    rather than posting via :attr:`content`.  If :attr:`ds_location`
    is set, it takes precedence over :attr:`content`.'''

    def __init__(self, obj, id, label, mimetype=None, versionable=False,
            state='A', format=None, control_group='M', checksum=None, checksum_type="MD5"):
                        
        self.obj = obj
        self.id = id

        if mimetype is None:
            mimetype = self.default_mimetype

        self.defaults = {
            'label': label,
            'mimetype': mimetype,
            'versionable': versionable,
            'state' : state,
            'format': format,
            'control_group': control_group,
            'checksum': checksum,
            'checksumType': checksum_type,
        }
        self._info = None
        self._content = None
        # for unversioned datastreams, store a copy of data pulled
        # from fedora in case undo save is required
        self._info_backup = None
        self._content_backup = None

        self.info_modified = False
        self.digest = None
        self.checksum_modified = False
        
        # Flag to indicate whether this datastream exists in fedora.
        # Assume false until/unless we can confirm otherwise.
	self.exists = False
        
        if not self.obj._create:
            # If this datastream belongs to an existing object, check 
            # to see if the datastream actually exists.
            if self.obj.ds_list.has_key(id):
                self.exists = True
    
    @property
    def info(self):
        # pull datastream profile information from Fedora, but only when accessed
        if self._info is None:
            if not self.exists:
                self._info = self._bootstrap_info()
            else:
                self._info = self.obj.getDatastreamProfile(self.id)
        return self._info

    def _bootstrap_info(self):
        profile = DatastreamProfile()
        profile.state = self.defaults['state']
        profile.mimetype = self.defaults['mimetype']
        profile.control_group = self.defaults['control_group']
        profile.versionable = self.defaults['versionable']
        profile.checksum_type = self.defaults['checksumType']
        if self.defaults.get('label', None):
            profile.label = self.defaults['label']
        if self.defaults.get('format', None):
            profile.format = self.defaults['format']
        return profile

    def _get_content(self):
        # Pull datastream content from Fedora and return it as a string, but
        # only when accessed. Note that this will load the entire datastream
        # contents into memory as a string. This is probably a bad idea for
        # large files. Thus:
        # TODO: Once we have an eulfedora.api call that returns
        # iterable chunks of datastream content, we need to either update
        # this property or add another to expose that iterable chunk
        # functionality at this layer.
        if self._content is None:
            if not self.exists:
                self._content = self._bootstrap_content()
            else:
                data, url = self.obj.api.getDatastreamDissemination(self.obj.pid, self.id)
                self._content = self._convert_content(data, url)
                # calculate and store a digest of the current datastream text content
                self.digest = self._content_digest()
        return self._content
    def _set_content(self, val):
        # if datastream is not versionable, grab contents before updating
        if not self.versionable:
            self._get_content()
        self._content = val
    content = property(_get_content, _set_content, None,
        '''contents of the datastream; for existing datastreams,
        content is only pulled from Fedora when first requested, and
        cached after first access; can be used to set or update
        datastream contents by means of text content or a file-like
        object.  For example, if you have a :class:`DigitalObject`
        subclass with a :class:`FileDatastream` defined as ``image``::

            with open(filename) as imgfile:
                myobj.image.content = imgfile

        For an alternate method to set datastream content, see
        :attr:`ds_location`.''')

    def _convert_content(self, data, url):
        # convert output of getDatastreamDissemination into the expected content type
        return data

    def _bootstrap_content(self):
        return None

    def _content_as_node(self):
        # used for serializing inline xml datastreams at ingest
        return None

    def _raw_content(self):
        # return datastream content in the appropriate format to be saved to Fedora
        # (normally, either a string or a file); used for serializing
        # managed datastreams for ingest and save and generating a hash
        # NOTE: if you override so this does not return a string, you may
        # also need to override _content_digest and/or isModified
        if self.content is None:
            return None
        if hasattr(self.content, 'serialize'):
            return str(self.content.serialize())
        else:
            return str(self.content)

    def isModified(self):
        """Check if either the datastream content or profile fields have changed
        and should be saved to Fedora.
        
        :rtype: boolean
        """
        return self.info_modified or self._content_digest() != self.digest

    def _content_digest(self):
        # generate a hash of the content so we can easily check if it has changed and should be saved
        return hashlib.sha1(self._raw_content()).hexdigest()

    ### access to datastream profile fields; tracks if changes are made for saving to Fedora

    def _get_label(self):
        return self.info.label
    def _set_label(self, val):
        self.info.label = val
        self.info_modified = True    
    label = property(_get_label, _set_label, None, "datastream label")
    
    def _get_mimetype(self):
        return self.info.mimetype
    def _set_mimetype(self, val):
        self.info.mimetype = val
        self.info_modified = True
    mimetype = property(_get_mimetype, _set_mimetype, None, "datastream mimetype")

    def _get_versionable(self):
        return self.info.versionable
    def _set_versionable(self, val):
        self.info.versionable = val
        self.info_modified = True
    versionable = property(_get_versionable, _set_versionable, None,
        "boolean; indicates if Fedora is configured to version the datastream")

    def _get_state(self):
        return self.info.state
    def _set_state(self, val):
        self.info.state = val
        self.info_modified = True
    state = property(_get_state, _set_state, None, "datastream state (Active/Inactive/Deleted)")

    def _get_format(self):
        return self.info.format
    def _set_format(self, val):
        self.info.format = val
        self.info_modified = True
    format = property(_get_format, _set_format, "datastream format URI")
    
    def _get_checksum(self):
        return self.info.checksum
    def _set_checksum(self, val):
        self.info.checksum = val
        self.info_modified = True
        self.checksum_modified = True
    checksum = property(_get_checksum, _set_checksum, "datastream checksum")
    
    def _get_checksumType(self):
        return self.info.checksum_type
    def _set_checksumType(self, val):
        self.info.checksum_type = val
        self.info_modified = True
    checksum_type = property(_get_checksumType, _set_checksumType, "datastream checksumType")

    # read-only info properties

    @property 
    def control_group(self):
        return self.info.control_group

    @property
    def created(self):
        return self.info.created

    @property
    def size(self):
        'Size of the datastream content'
        return self.info.size

    @property
    def modified(self):
        # FIXME: not actually available in datastreamProfile !!
        return self.info.modified

    def last_modified(self):
        # FIXME: **preliminary** actual last-modified, since the above does not
        # actually work - should probably cache ds history...
        history = self.obj.api.getDatastreamHistory(self.obj.pid, self.id)
        return history.datastreams[0].createDate # fedora returns with most recent first

    def save(self, logmessage=None):
        """Save datastream content and any changed datastream profile
        information to Fedora.

        :rtype: boolean for success
        """
        save_opts = {}
        if self.info_modified:
            if self.label:
                save_opts['dsLabel'] = self.label
            if self.mimetype:
                save_opts['mimeType'] = self.mimetype
            if self.versionable is not None:
                save_opts['versionable'] = self.versionable
            if self.state:
                save_opts['dsState'] = self.state
            if self.format:
                save_opts['formatURI'] = self.format
            if self.checksum:
                if(self.checksum_modified):
                    save_opts['checksum'] = self.checksum
            if self.checksum_type:
                save_opts['checksumType'] = self.checksum_type
            # FIXME: should be able to handle checksums
        # NOTE: as of Fedora 3.2, updating content without specifying mimetype fails (Fedora bug?)
        if 'mimeType' not in save_opts.keys():
            # if datastreamProfile has not been pulled from fedora, use configured default mimetype
            if self._info is not None:
                save_opts['mimeType'] = self.mimetype
            else:
                save_opts['mimeType'] = self.defaults['mimetype']

        # if datastream location has been set, use that for content
        # otherwise, use local content (if any)
        if self.ds_location is not None:
            save_opts['dsLocation'] = self.ds_location
        else:
            save_opts['content'] = self._raw_content()

        if self.exists:
            # if not versionable, make a backup to back out changes if object save fails
            if not self.versionable:
                self._backup()
                
            # if this datastream already exists, use modifyDatastream API call
            success, msg = self.obj.api.modifyDatastream(self.obj.pid, self.id, 
                    logMessage=logmessage, **save_opts)
        else:
            # if this datastream does not yet exist, add it
            success, msg = self.obj.api.addDatastream(self.obj.pid, self.id,
                    controlGroup=self.defaults['control_group'],
                    logMessage=logmessage, **save_opts)

            # clean-up required for object info after adding a new datastream
            if success:
                # update exists flag - if add succeeded, the datastream exists now
                self.exists = True
                # if the datastream content is a file-like object, clear it out
                # (we don't want to attempt to save the current file contents again,
                # particularly since the file is not guaranteed to still be open)
                if 'content' in save_opts and hasattr(save_opts['content'], 'read'):
                    self._content = None
                    self._content_modified = False      
 
        if success:
            # update modification indicators
            self.info_modified = False
            self.checksum_modified = False
            self.digest = self._content_digest()
            # clear out ds location
            self.ds_location = None
            
        return success      # msg ?

    def _backup(self):
        info = self.obj.getDatastreamProfile(self.id)
        self._info_backup = { 'dsLabel': info.label,
                              'mimeType': info.mimetype,
                              'versionable': info.versionable,
                              'dsState': info.state,
                              'formatURI': info.format,
                              'checksumType': info.checksum_type,
                              'checksum': info.checksum }

        data, url = self.obj.api.getDatastreamDissemination(self.obj.pid, self.id)
        self._content_backup = data

    def undo_last_save(self, logMessage=None):
        """Undo the last change made to the datastream content and profile, effectively 
        reverting to the object state in Fedora as of the specified timestamp.

        For a versioned datastream, this will purge the most recent datastream.
        For an unversioned datastream, this will overwrite the last changes with
        a cached version of any content and/or info pulled from Fedora.
        """        
        # NOTE: currently not clearing any of the object caches and backups
        # of fedora content and datastream info, as it is unclear what (if anything)
        # should be cleared

        if self.versionable:
            # if this is a versioned datastream, get datastream history
            # and purge the most recent version 
            history = self.obj.api.getDatastreamHistory(self.obj.pid, self.id)
            last_save = history.datastreams[0].createDate   # fedora returns with most recent first
            success, timestamps = self.obj.api.purgeDatastream(self.obj.pid, self.id,
                                                datetime_to_fedoratime(last_save),
                                                logMessage=logMessage)
            return success
        else:
            # for an unversioned datastream, update with any content and info
            # backups that were pulled from Fedora before any modifications were made
            args = {}
            if self._content_backup is not None:
                args['content'] = self._content_backup
            if self._info_backup is not None:
                args.update(self._info_backup)
            success, msg = self.obj.api.modifyDatastream(self.obj.pid, self.id,
                            logMessage=logMessage, **args)
            return success

    def get_chunked_content(self, chunksize=4096):
        '''Generator that returns the datastream content in chunks, so
        larger datastreams can be used without reading the entire
        contents into memory.'''
        # get the datastream dissemination, but return the actual http response 
        response = self.obj.api.getDatastreamDissemination(self.obj.pid, self.id,
                                                           return_http_response=True)
        # read and yield the response in chunks
        while True:
            chunk = response.read(chunksize)
            if not chunk:
                return
            yield chunk


class Datastream(object):
    """Datastream descriptor to simplify configuration and access to datastreams
    that belong to a particular :class:`DigitalObject`.

    When accessed, will initialize a :class:`DatastreamObject` and cache it on
    the :class:`DigitalObject` that it belongs to.

    Example usage::

        class MyDigitalObject(DigitalObject):
            text = Datastream("TEXT", "Text content", defaults={'mimetype': 'text/plain'})

    All other configuration defaults are passed on to the :class:`DatastreamObject`.
    """

    _datastreamClass = DatastreamObject

    def __init__(self, id, label, defaults={}):
        self.id = id
        self.label = label 
        self.datastream_args = defaults
        
        #self.label = label
        #self.datastream_defaults = defaults

    def __get__(self, obj, objtype): 
        if obj is None:
            return self
        if obj.dscache.get(self.id, None) is None:
            obj.dscache[self.id] = self._datastreamClass(obj, self.id, self.label, **self.datastream_args)
        return obj.dscache[self.id]

    @property
    def default_mimetype(self):
        mimetype = self.datastream_args.get('mimetype', None)
        if mimetype:
            return mimetype
        ds_cls = self._datastreamClass
        return ds_cls.default_mimetype

    @property
    def default_format_uri(self):
        return self.datastream_args.get('format', None)

    # set and delete not implemented on datastream descriptor
    # - delete would only make sense for optional datastreams, not yet needed
    # - saving updated content to fedora handled by datastream object


class XmlDatastreamObject(DatastreamObject):
    """Extends :class:`DatastreamObject` in order to initialize datastream content
    as an instance of a specified :class:`~eulxml.xmlmap.XmlObject`.

    See :class:`DatastreamObject` for more details.  Has one additional parameter:

    :param objtype: xml object type to use for datastream content; if not specified,
        defaults to :class:`~eulxml.xmlmap.XmlObject`
    """
    
    default_mimetype = "text/xml"

    def __init__(self, obj, id, label, objtype=xmlmap.XmlObject, **kwargs):
        self.objtype = objtype
        super(XmlDatastreamObject, self).__init__(obj, id, label, **kwargs)

    # FIXME: override _set_content to handle setting full xml content?

    def _convert_content(self, data, url):
        return parse_xml_object(self.objtype, data, url)

    def _bootstrap_content(self):
        return self.objtype()

    def _content_as_node(self):
        return self.content.node


class XmlDatastream(Datastream):
    """XML-specific version of :class:`Datastream`.  Datastreams are initialized
    as instances of :class:`XmlDatastreamObject`.  An additional, optional
    parameter ``objtype`` is passed to the Datastream object to configure the
    type of :class:`eulxml.xmlmap.XmlObject` that should be used for datastream
    content.

    Example usage::

        from eulxml.xmlmap.dc import DublinCore
        
        class MyDigitalObject(DigitalObject):
            extra_dc = XmlDatastream("EXTRA_DC", "Dublin Core", DublinCore)

        my_obj = repo.get_object("example:1234", type=MyDigitalObject)
        my_obj.extra_dc.content.title = "Example object"
        my_obj.save(logMessage="automatically setting dc title")
    """
    _datastreamClass = XmlDatastreamObject
    
    def __init__(self, id, label, objtype=None, defaults={}):        
        super(XmlDatastream, self).__init__(id, label, defaults)
        self.datastream_args['objtype'] = objtype


class RdfDatastreamObject(DatastreamObject):
    """Extends :class:`DatastreamObject` in order to initialize datastream content
    as an `rdflib <http://pypi.python.org/pypi/rdflib/>`_ RDF graph.
    """
    default_mimetype = "application/rdf+xml"
    # prefixes for namespaces expected to be used in RELS-EXT
    default_namespaces = {
        'fedora-model': 'info:fedora/fedora-system:def/model#',
        'fedora-rels-ext': 'info:fedora/fedora-system:def/relations-external#',
        'oai': 'http://www.openarchives.org/OAI/2.0/'
        }

    # FIXME: override _set_content to handle setting content?
    def _convert_content(self, data, url):
        return self._bind_prefixes(parse_rdf(data, url))

    def _bootstrap_content(self):
        return self._bind_prefixes(RdfGraph())

    def _bind_prefixes(self, graph):
        # bind any specified prefixes so that serialized xml will be human-readable
        for prefix, namespace in self.default_namespaces.iteritems():
            graph.bind(prefix, namespace)
        return graph

    def _content_as_node(self):
        graph = self.content
        data = graph.serialize()
        obj = xmlmap.load_xmlobject_from_string(data)
        return obj.node

    def replace_uri(self, src, dest):
        """Replace a uri reference everywhere it appears in the graph with
        another one. It could appear as the subject, predicate, or object of
        a statement, so for each position loop through each statement that
        uses the reference in that position, remove the old statement, and
        add the replacement. """

        # NB: The hypothetical statement <src> <src> <src> will be removed
        # and re-added several times. The subject block will remove it and
        # add <dest> <src> <src>. The predicate block will remove that and
        # add <dest> <dest> <src>. The object block will then remove that
        # and add <dest> <dest> <dest>.

        # NB2: The list() call here is necessary. .triples() is a generator:
        # It calculates its matches as it progressively iterates through the
        # graph. Actively changing the graph inside the for loop while the
        # generator is in the middle of examining it risks invalidating the
        # generator and could conceivably make it Just Break, depending on
        # the implementation of .triples(). Wrapping .triples() in a list()
        # forces it to exhaust the generator, running through the entire
        # graph to calculate the list of matches before continuing to the
        # for loop.

        subject_triples = list(self.content.triples((src, None, None)))
        for s, p, o in subject_triples:
            self.content.remove((src, p, o))
            self.content.add((dest, p, o))

        predicate_triples = list(self.content.triples((None, src, None)))
        for s, p, o in predicate_triples:
            self.content.remove((s, src, o))
            self.content.add((s, dest, o))

        object_triples = list(self.content.triples((None, None, src)))
        for s, p, o in object_triples:
            self.content.remove((s, p, src))
            self.content.add((s, p, dest))

    def _prepare_ingest(self):
        """If the RDF datastream refers to the object by the default dummy
        uriref then we need to replace that dummy reference with a real one
        before we ingest the object."""

        # see also commentary on DigitalObject.DUMMY_URIREF
        self.replace_uri(self.obj.DUMMY_URIREF, self.obj.uriref)


class RdfDatastream(Datastream):
    """RDF-specific version of :class:`Datastream` for accessing datastream
    content as an `rdflib <http://pypi.python.org/pypi/rdflib/>`_ RDF graph.
    Datastreams are initialized as instances of
    :class:`RdfDatastreamObject`.

    Example usage::

        from rdflib import RDFS, Literal

        class MyDigitalObject(DigitalObject):
            extra_rdf = RdfDatastream("EXTRA_RDF", "an RDF graph of stuff")

        my_obj = repo.get_object("example:4321", type=MyDigitalObject)
        my_obj.extra_rdf.content.add((my_obj.uriref, RDFS.comment,
                                      Literal("This is an example object.")))
        my_obj.save(logMessage="automatically setting rdf comment")
    """
    _datastreamClass = RdfDatastreamObject


class FileDatastreamObject(DatastreamObject):
    """Extends :class:`DatastreamObject` in order to allow setting and reading
    datastream content as a file. To update contents, set datastream content
    property to a new file object. For example::

        class ImageObject(DigitalObject):
            image = FileDatastream('IMAGE', 'image datastream', defaults={
                'mimetype': 'image/png'
            })
    
    Then, with an instance of ImageObject::

        obj.image.content = open('/path/to/my/file')
        obj.save()
    """

    _content_modified = False

    def _raw_content(self):
        # return the content in the format needed to save to Fedora
        # if content has not been loaded, return None (no changes)
        if self._content is None:
            return None
        else:
            return self.content     # return the file itself (handled by upload/save API calls)

    def _convert_content(self, data, url):
        # for now, using stringio to return a file-like object
        # NOTE: will require changes (here and in APIs) to handle large files
        return cStringIO.StringIO(data)

    # redefine content property to override set_content to set a flag when modified
    def _get_content(self):
        super(FileDatastreamObject, self)._get_content()
        return self._content    
    def _set_content(self, val):
        super(FileDatastreamObject, self)._set_content(val)
        self._content_modified = True        
    content = property(_get_content, _set_content, None,
        "contents of the datastream; only pulled from Fedora when accessed, cached after first access")

    def _content_digest(self):
        # don't attempt to create a checksum of the file content
        pass
    
    def isModified(self):
        return self.info_modified or self._content_modified
    

class FileDatastream(Datastream):
    """File-based content version of :class:`Datastream`.  Datastreams are
    initialized as instances of :class:`FileDatastreamObject`.
    """
    _datastreamClass = FileDatastreamObject


class DigitalObjectType(type):
    """A metaclass for :class:`DigitalObject`.
    
    All this does for now is find Datastream objects from parent classes
    and those defined on the class itself and collect them into a
    _defined_datastreams dictionary on the class. Using this, clients (or,
    more likely, internal library code) can more easily introspect the
    datastreams defined in code for the object.
    """

    _registry = {}

    def __new__(cls, name, bases, defined_attrs):
        datastreams = {}
        local_datastreams = {}
        use_attrs = defined_attrs.copy()

        for base in bases:
            base_ds = getattr(base, '_defined_datastreams', None)
            if base_ds:
                datastreams.update(base_ds)

        for attr_name, attr_val in defined_attrs.items():
            if isinstance(attr_val, Datastream):
                local_datastreams[attr_name] = attr_val

        use_attrs['_local_datastreams'] = local_datastreams

        datastreams.update(local_datastreams)
        use_attrs['_defined_datastreams'] = datastreams

        super_new = super(DigitalObjectType, cls).__new__
        new_class = super_new(cls, name, bases, use_attrs)

        new_class_name = '%s.%s' % (new_class.__module__, new_class.__name__)
        DigitalObjectType._registry[new_class_name] = new_class

        return new_class

    @property
    def defined_types(self):
        return DigitalObjectType._registry.copy()


class DigitalObject(object):
    """
    A single digital object in a Fedora respository, with methods and
    properties to easy creating, accessing, and updating a Fedora
    object or any of its component parts, with pre-defined datastream
    mappings for the standard Fedora Dublin Core
    (:attr:`~eulfedora.models.DigitalObject.dc`) and RELS-EXT
    (:attr:`~eulfedora.models.DigitalObject.rels_ext`) datastreams.

    .. Note::

      If you want idiomatic access to other datastreams, consider
      extending :class:`DigitalObject` and defining your own
      datastreams using :class:`XmlDatastream`,
      :class:`RdfDatastream`, or :class:`FileDatastream` as
      appropriate.
    
    """

    __metaclass__ = DigitalObjectType

    default_pidspace = None
    """Default namespace to use when generating new PIDs in
        :meth:`get_default_pid` (by default, calls Fedora getNextPid,
        which will use Fedora-configured namespace if default_pidspace
        is not set)."""

    OWNER_ID_SEPARATOR = ','
    '''Owner ID separator for multiple owners.  Should match the
    OWNER-ID-SEPARATOR configured in Fedora.
    For more detail, see https://jira.duraspace.org/browse/FCREPO-82
    '''

    dc = XmlDatastream("DC", "Dublin Core", DublinCore, defaults={
            'control_group': 'X',
            'format': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
        })
    ''':class:`XmlDatastream` for the required Fedora **DC** datastream;
    datastream content will be automatically loaded as an instance of
    :class:`eulxml.xmlmap.dc.DublinCore`'''
    rels_ext = RdfDatastream("RELS-EXT", "External Relations", defaults={
            'control_group': 'X',
            'format': 'info:fedora/fedora-system:FedoraRELSExt-1.0',
        })
    ''':class:`RdfDatastream` for the standard Fedora **RELS-EXT** datastream'''

    def __init__(self, api, pid=None, create=False, default_pidspace=None):
        self.api = api
        self.dscache = {}       # accessed by DatastreamDescriptor to store and cache datastreams
        self._risearch = None

        if default_pidspace:
            try:
                self.default_pidspace = default_pidspace
            except AttributeError:
                # allow extending classes to make default_pidspace a custom property,
                # but warn in case of conflict
                logger.warn("Failed to set requested default_pidspace %s" % default_pidspace)
        # cache object profile, track if it is modified and needs to be saved
        self._info = None
        self.info_modified = False
        
        # datastream list from fedora
        self._ds_list = None
        
        # object history
        self._history = None
        self._methods = None

        # pid = None signals to create a new object, using a default pid
        # generation function.
        if pid is None:
            # self.get_default_pid is probably the method defined elsewhere
            # in this class. Barring clever hanky-panky, it should be
            # reliably callable.
            pid = self.get_default_pid
        elif isinstance(pid, basestring) and \
                 pid.startswith('info:fedora/'): # passed a uri
            pid = pid[len('info:fedora/'):]

        # callable(pid) signals a function to call to obtain a pid if and
        # when one is needed
        if callable(pid):
            create = True

        self.pid = pid

        # self._create is True when we should create (ingest) this object in
        # fedora on first save(), False if we should assume it's already
        # there. Note that if pid is callable, create is always True (for
        # which see above)
        self._create = bool(create)

        if create:
            self._init_as_new_object()

    def _init_as_new_object(self):
        for cmodel in getattr(self, 'CONTENT_MODELS', ()):
            self.rels_ext.content.add((self.uriref, modelns.hasModel,
                                       URIRef(cmodel)))

    @property
    def risearch(self):
        "Instance of :class:`eulfedora.api.ResourceIndex`, with the same root url and credentials"
        if self._risearch is None:
            self._risearch = ResourceIndex(self.api.opener)
        return self._risearch

    def get_object(self, pid, type=None):
        '''Initialize and return a new
        :class:`~eulfedora.models.DigitalObject` instance from the same
        repository, passing along the connection credentials in use by
        the current object.  If type is not specified, the current
        DigitalObject class will be used.

        :param pid: pid of the object to return
        :param type: (optional) :class:`~eulfedora.models.DigitalObject`
           type to initialize and return
        '''
        if type is None:
            type = self.__class__
        return type(self.api, pid)

    def __str__(self):
        if callable(self.pid):
            return '(generated pid; uningested)'
        elif self._create:
            return self.pid + ' (uningested)'
        else:
            return self.pid

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, str(self))

    def get_default_pid(self):
        '''Get the next default pid when creating and ingesting a new
        DigitalObject instance without specifying a pid.  By default,
        calls :meth:`ApiFacade.getNextPID` with the configured class
        default_pidspace (if specified) as the pid namespace.

        If your project requires custom pid logic (e.g., object pids
        are based on an external pid generator), you should extend
        DigitalObject and override this method.'''
        # This function is used by __init__ as a default pid generator if
        # none is specified. If you get the urge to override it, make sure
        # it still works there.
        kwargs = {}
        if self.default_pidspace  is not None:
            kwargs['namespace'] = self.default_pidspace
        data, url = self.api.getNextPID(**kwargs)
        nextpids = parse_xml_object(NewPids, data, url)
        return nextpids.pids[0]

    @property
    def pidspace(self):
        "Fedora pidspace of this object"
        if callable(self.pid):
            return None
        ps, pid = self.pid.split(':', 1)
        return ps

    # This dummy pid stuff is ugly. I'd rather not need it. Every now and
    # then, though, something needs a PID or URI for a brand-new object
    # (i.e., with a callable self.pid) before we've even had a chance to
    # generate one. In particular, if we want to add statements to an
    # object's RELS-EXT, then the the object URI needs to be the subject of
    # those statements. We can't just generate the PID early because we get
    # PIDs from ARKs, and those things stick around. Also, most objects get
    # RELS-EXT statements right as we create them anyway (see references to
    # CONTENT_MODELS in _init_as_new_object()), so calling self.pid as soon
    # as we need a uri would be essentially equivalent to "at object
    # creation," which negates the whole point of lazy callable pids.
    #
    # So anyway, this DUMMY_PID gives us something we can use as a pid for
    # new objects, with the understanding that we have to clean it up to use
    # the real pid in obj._prepare_ingest(), which is called after we've
    # committed to trying to ingest the object, and thus after self.pid has
    # been called and replaced with a real string pid. DatastreamObject
    # subclasses can do this in their own _prepare_ingest() methods.
    # RELS-EXT (and all other RDF datastreams for that matter) get that
    # implemented in RdfDatastreamObject above.
    DUMMY_PID = 'TEMP:DUMMY_PID'
    DUMMY_URIREF = URIRef('info:fedora/' + DUMMY_PID)

    @property
    def uri(self):
        "Fedora URI for this object (``info:fedora/foo:###`` form of object pid) "
        use_pid = self.pid
        if callable(use_pid):
            use_pid = self.DUMMY_PID
        return 'info:fedora/' + use_pid

    @property
    def uriref(self):
        "Fedora URI for this object, as an rdflib URI object"
        return URIRef(self.uri)

    @property
    def info(self):
        # pull object profile information from Fedora, but only when accessed
        if self._info is None:
            self._info = self.getProfile()
        return self._info
    
    # object info properties

    def _get_label(self):
        return self.info.label
    def _set_label(self, val):
        # Fedora object label property has a maximum of 255 characters
        if len(val) > 255:
            logger.warning('Attempting to set object label for %s to a value longer than 255 character max (%d); truncating' \
                % (self.pid, len(val)))
            val = val[0:255]

        # if the new value is different, track object information modification for next save
        if self.info.label != val:
            self.info_modified = True
        self.info.label = val
    label = property(_get_label, _set_label, None, "object label")

    def _get_owner(self):
        return self.info.owner
    def _set_owner(self, val):
        self.info.owner = val
        self.info_modified = True
    owner = property(_get_owner, _set_owner, None, "object owner")

    @property
    def owners(self):
        '''Read-only list of object owners, separated by the configured
        :attr:`OWNER_ID_SEPARATOR`, with whitespace stripped.'''
        return [o.strip() for o in self.owner.split(self.OWNER_ID_SEPARATOR)]

    def _get_state(self):
        return self.info.state
    def _set_state(self, val):
        self.info.state = val
        self.info_modified = True
    state = property(_get_state, _set_state, None, "object state (Active/Inactive/Deleted)")

    # read-only info properties
    @property       
    def created(self):
        return self.info.created

    @property
    def modified(self):
        return self.info.modified

    @property
    def exists(self):
        """:type: bool

        True when the object actually exists (and can be accessed by
        the current user) in Fedora
        """

        # If we made the object under the pretext that it doesn't exist in
        # fedora yet, then assume it doesn't exist in fedora yet.
        if self._create:
            return False

        # If we can get a valid object profile, regardless of its contents,
        # then this object exists. If not, then it doesn't. 
        try:
            self.getProfile()
            return True
        except RequestFailed:
            return False

    @property
    def has_requisite_content_models(self):
        ''':type: bool

        True when the current object has the expected content models
        for whatever subclass of :class:`DigitalObject` it was
        initialized as.'''
        for cmodel in getattr(self, 'CONTENT_MODELS', ()):
            if not self.has_model(cmodel):
                return False
        return True

    def getDatastreamProfile(self, dsid):
        """Get information about a particular datastream belonging to this object.

        :param dsid: datastream id
        :rtype: :class:`DatastreamProfile`
        """
        # NOTE: used by DatastreamObject
        if self._create:
            return None

        data, url = self.api.getDatastream(self.pid, dsid)
        return parse_xml_object(DatastreamProfile, data, url)

    @property
    def history(self):
        if self._history is None:
            self.getHistory()
        return self._history

    def getHistory(self):
        if self._create:
            return None
        else:
            data, url = self.api.getObjectHistory(self.pid)
            history = parse_xml_object(ObjectHistory, data, url)
        self._history = [c for c in history.changed]
        return history

    def getProfile(self):    
        """Get information about this object (label, owner, date created, etc.).

        :rtype: :class:`ObjectProfile`
        """
        if self._create:
            return ObjectProfile()
        else:
            data, url = self.api.getObjectProfile(self.pid)
            return parse_xml_object(ObjectProfile, data, url)

    def _saveProfile(self, logMessage=None):
        if self._create:
            raise Exception("can't save profile information for a new object before it's ingested.")

        saved = self.api.modifyObject(self.pid, self.label, self.owner, self.state, logMessage)
        if saved:
            # profile info is no longer different than what is in Fedora
            self.info_modified = False
        return saved
    
    def save(self, logMessage=None):
        """Save to Fedora any parts of this object that have been
        modified (including object profile attributes such as
        :attr:`label`, :attr:`owner`, or :attr:`state`, and any
        changes to datastream content or datastream properties).  If a
        failure occurs at any point on saving any of the parts of the
        object, will back out any changes that have been made and
        raise a :class:`DigitalObjectSaveFailure` with information
        about where the failure occurred and whether or not it was
        recoverable.

        If the object is new, ingest it. If object profile information has
        been modified before saving, this data is used in the ingest.
        Datastreams are initialized to sensible defaults: XML objects are
        created using their default constructor, and RDF graphs start
        empty. If they're updated before saving then those updates are
        included in the initial version. Datastream profile information is
        initialized from defaults specified in the :class:`Datastream`
        declaration, though it too can be overridden prior to the initial
        save.
        """
        
        if self._create:
            self._prepare_ingest()
            self._ingest(logMessage)
        else:
            self._save_existing(logMessage)
        
        #No errors, then return true
        return True

    def _save_existing(self, logMessage):
        # save an object that has already been ingested into fedora

        # - list of datastreams that should be saved
        to_save = [ds for ds, dsobj in self.dscache.iteritems() if dsobj.isModified()]
        # - track successfully saved datastreams, in case roll-back is necessary
        saved = []
        # save modified datastreams
        for ds in to_save:
            # in eulfedora 0.16 and before, add/modify datastream returned True/False
            # in later versions, it throws an exception 
            try:
                ds_saved = self.dscache[ds].save(logMessage)
            except RequestFailed:
                logger.error('Failed to save %s/%s' % (self.pid, ds))
                ds_saved = False
                
            if ds_saved:
                saved.append(ds)
            else:
                # save datastream failed - back out any changes that have been made
                cleaned = self._undo_save(saved, 
                                          "failed saving %s, rolling back changes" % ds)
                raise DigitalObjectSaveFailure(self.pid, ds, to_save, saved, cleaned)

        # NOTE: to_save list in exception will never include profile; should it?

        # FIXME: catch exceptions on save, treat same as failure to save (?)

        # save object profile (if needed) after all modified datastreams have been successfully saved
        if self.info_modified:
            try:
                profile_saved = self._saveProfile(logMessage)
            except RequestFailed:
                logger.error('Failed to save object profile for %s' % self.pid)
                profile_saved = False

            if not profile_saved:
                cleaned = self._undo_save(saved, "failed to save object profile, rolling back changes")
                raise DigitalObjectSaveFailure(self.pid, "object profile", to_save, saved, cleaned)
            

    def _undo_save(self, datastreams, logMessage=None):
        """Takes a list of datastreams and a datetime, run undo save on all of them,
        and returns a list of the datastreams where the undo succeeded.

        :param datastreams: list of datastream ids (should be in self.dscache)
        :param logMessage: optional log message
        """
        return [ds for ds in datastreams if self.dscache[ds].undo_last_save(logMessage)]

    def _prepare_ingest(self):
        # This should only ever be called on newly-created objects, and only
        # immediately before ingest. It's used to clean up any rough edges
        # left over from being hewn from raw bits (instead of loaded from
        # the repo, like most other DigitalObjects are). In particular, see
        # the comments by DigitalObject.DUMMY_PID.

        if callable(self.pid):
            self.pid = self.pid()

        for dsname, ds in self._defined_datastreams.items():
            dsobj = getattr(self, dsname)
            if hasattr(dsobj, '_prepare_ingest'):
                dsobj._prepare_ingest()


    def _ingest(self, logMessage):
        foxml = self._build_foxml_for_ingest()
        returned_pid = self.api.ingest(foxml, logMessage)

        if returned_pid != self.pid:
            msg = ('fedora returned unexpected pid "%s" when trying to ' + 
                   'ingest object with pid "%s"') % \
                  (returned_pid, self.pid)
            raise Exception(msg)

        # then clean up the local object so that self knows it's dealing
        # with an ingested object now
        self._create = False
        self._info = None
        self.info_modified = False
        self.dscache = {}

    def _build_foxml_for_ingest(self, pretty=False):
        doc = self._build_foxml_doc()

        print_opts = {'encoding' : 'UTF-8'}
        if pretty: # for easier debug
            print_opts['pretty_print'] = True
        
        return etree.tostring(doc, **print_opts)

    FOXML_NS = 'info:fedora/fedora-system:def/foxml#'

    def _build_foxml_doc(self):
        # make an lxml element builder - default namespace is foxml, display with foxml prefix
        E = ElementMaker(namespace=self.FOXML_NS, nsmap={'foxml' : self.FOXML_NS })
        doc = E('digitalObject')
        doc.set('VERSION', '1.1')
        doc.set('PID', self.pid)
        doc.append(self._build_foxml_properties(E))
        
        # collect datastream definitions for ingest.
        for dsname, ds in self._defined_datastreams.items():
            dsobj = getattr(self, dsname)
            dsnode = self._build_foxml_datastream(E, ds.id, dsobj)
            if dsnode is not None:
                doc.append(dsnode)
        
        return doc

    def _build_foxml_properties(self, E):
        props = E('objectProperties')
        state = E('property')
        state.set('NAME', 'info:fedora/fedora-system:def/model#state')
        state.set('VALUE', self.state or 'A')
        props.append(state)

        if self.label:
            label = E('property')
            label.set('NAME', 'info:fedora/fedora-system:def/model#label')
            label.set('VALUE', self.label)
            props.append(label)
        
        if self.owner:
            owner = E('property')
            owner.set('NAME', 'info:fedora/fedora-system:def/model#ownerId')
            owner.set('VALUE', self.owner)
            props.append(owner)

        return props

    def _build_foxml_datastream(self, E, dsid, dsobj):

        # if we can't construct a content node then bail before constructing
        # any other nodes
        content_node = None
        if dsobj.control_group == 'X':
            content_node = self._build_foxml_inline_content(E, dsobj)
        elif dsobj.control_group == 'M':
            content_node = self._build_foxml_managed_content(E, dsobj)
        if content_node is None:
            return

        ds_xml = E('datastream')
        ds_xml.set('ID', dsid)
        ds_xml.set('CONTROL_GROUP', dsobj.control_group)
        ds_xml.set('STATE', dsobj.state)
        ds_xml.set('VERSIONABLE', str(dsobj.versionable).lower())

        ver_xml = E('datastreamVersion')
        ver_xml.set('ID', dsid + '.0')
        ver_xml.set('MIMETYPE', dsobj.mimetype)
        if dsobj.format:
            ver_xml.set('FORMAT_URI', dsobj.format)
        if dsobj.label:
            ver_xml.set('LABEL', dsobj.label)
            
        # Set the checksum, if available.
        #FIXME: Do this somewhere stuff somewhere else? Currently outside where the actual file content is attached....
        # if *either* a checksum or a checksum type is specified, set the contentDigest
        # - if checksum_type is set but not the actual checksum, Fedora should calculate it for us
        if dsobj.checksum or dsobj.checksum_type:
            digest_xml = E('contentDigest')
            if dsobj.checksum_type:
                digest_xml.set('TYPE', dsobj.checksum_type)
            else:
                # default to MD5 checksum if not specified
                digest_xml.set('TYPE', "MD5")
            if dsobj.checksum:
                digest_xml.set('DIGEST', dsobj.checksum)
            ver_xml.append(digest_xml)
        elif hasattr(dsobj._raw_content(), 'read'):
            # Content exists, but no checksum, so log a warning.
            # FIXME: probably need a better way to check this.
            logging.warning("Datastream ingested without a passed checksum or checksum type: %s/%s." % (self.pid, dsid))
            
        ds_xml.append(ver_xml)

        ver_xml.append(content_node)
        return ds_xml

    def _build_foxml_inline_content(self, E, dsobj):
        orig_content_node = dsobj._content_as_node()
        if orig_content_node is None:
            return

        content_container_xml = E('xmlContent')
        content_container_xml.append(orig_content_node)
        return content_container_xml

    def _build_foxml_managed_content(self, E, dsobj):
        content_uri = None
        if dsobj.ds_location:
            # if datastream has a location set, use that first
            content_uri = dsobj.ds_location
            uri_type = 'URL'
        else:
            # otherwise, check for local content and upload it
            content_s = dsobj._raw_content()
            if content_s is not None:
                content_uri = self.api.upload(content_s)
                uri_type = 'INTERNAL_ID'

        # stop if no content was found in either location
        if content_uri is None:
            return

        content_location = E('contentLocation')
        content_location.set('REF', content_uri)
        content_location.set('TYPE', uri_type)
        return content_location

    def _get_datastreams(self):
        """
        Get all datastreams that belong to this object.

        Returns a dictionary; key is datastream id, value is an :class:`ObjectDatastream`
        for that datastream.

        :rtype: dictionary
        """
        if self._create:
            # FIXME: should we default to the datastreams defined in code?
            return {}
        else:
            # NOTE: can be accessed as a cached class property via ds_list
            data, url = self.api.listDatastreams(self.pid)
            dsobj = parse_xml_object(ObjectDatastreams, data, url)
            return dict([ (ds.dsid, ds) for ds in dsobj.datastreams ])

    @property
    def ds_list(self):      # NOTE: how to name to distinguish from locally configured datastream objects?
        """
        Dictionary of all datastreams that belong to this object in Fedora.
        Key is datastream id, value is an :class:`ObjectDatastream` for that
        datastream.

        Only retrieved when requested; cached after first retrieval.
        """
        # FIXME: how to make access to a versioned ds_list ?

        if self._ds_list is None:
            self._ds_list = self._get_datastreams()
        return self._ds_list

    @property
    def methods(self):
        if self._methods is None:
            self.get_methods()
        return self._methods

    def get_methods(self):
        if self._create:
            return {}

        data, url = self.api.listMethods(self.pid)
        methods = parse_xml_object(ObjectMethods, data, url)
        self._methods = dict((sdef.pid, sdef.methods)
                             for sdef in methods.service_definitions)
        return self._methods

    def getDissemination(self, service_pid, method, params={}, return_http_response=False):
        return self.api.getDissemination(self.pid, service_pid, method, method_params=params,
                                         return_http_response=return_http_response)

    def getDatastreamObject(self, dsid):
        "Get any datastream on this object as a :class:`DatastreamObject`"
        if dsid in self.ds_list:
            ds_info = self.ds_list[dsid]
            # FIXME: can we take advantage of Datastream descriptor? or at least use dscashe ?

            # if datastream mimetype matches one of our base datastream objects, use it
            if ds_info.mimeType == XmlDatastreamObject.default_mimetype:
                dsobj_type = XmlDatastreamObject
            elif ds_info.mimeType == RdfDatastreamObject.default_mimetype:
                dsobj_type = RdfDatastreamObject
            else:
                # default to base datastream object class
                dsobj_type = DatastreamObject

            return dsobj_type(self, dsid, label=ds_info.label, mimetype=ds_info.mimeType)
        # exception if not ?

    def add_relationship(self, rel_uri, object):
        """
        Add a new relationship to the RELS-EXT for this object.
        Calls :meth:`API_M.addRelationship`.

        Example usage::

            isMemberOfCollection = 'info:fedora/fedora-system:def/relations-external#isMemberOfCollection'
            collection_uri = 'info:fedora/foo:456'
            object.add_relationship(isMemberOfCollection, collection_uri)

        :param rel_uri: URI for the new relationship
        :param object: related object; can be :class:`DigitalObject` or string; if
                        string begins with info:fedora/ it will be treated as
                        a resource, otherwise it will be treated as a literal
        :rtype: boolean
        """  
        if isinstance(rel_uri, URIRef):
            rel_uri = unicode(rel_uri)

        obj_is_literal = True
        if isinstance(object, DigitalObject):
            object = object.uri
            obj_is_literal = False
        elif isinstance(object, str) and object.startswith('info:fedora/'):
            obj_is_literal = False

        # this call will change RELS-EXT, possibly creating it if it's
        # missing. remove any cached info we have for that datastream.
        if 'RELS-EXT' in self.dscache:
            del self.dscache['RELS-EXT']
        self._ds_list = None

        return self.api.addRelationship(self.pid, rel_uri, object, obj_is_literal)

    def has_model(self, model):
        """
        Check if this object subscribes to the specified content model.

        :param model: URI for the content model, as a string
                    (currently only accepted in ``info:fedora/foo:###`` format)
        :rtype: boolean
        """
        # TODO:
        # - accept DigitalObject for model?
        # - convert model pid to info:fedora/ form if not passed in that way?
        try:
            rels = self.rels_ext.content
        except RequestFailed, e:
            # if rels-ext can't be retrieved, confirm this object does not have a RELS-EXT
            # (in which case, it does not subscribe to the specified content model)            
            if "RELS-EXT" not in self.ds_list.keys():
                return False
            else:
                raise
            
        st = (self.uriref, modelns.hasModel, URIRef(model))
        return st in rels

    def get_models(self):
        """
        Get a list of content models the object subscribes to.
        """
        try:
            rels = self.rels_ext.content
        except RequestFailed, e:
            # if rels-ext can't be retrieved, confirm this object does not have a RELS-EXT
            # (in which case, it does not have any content models)
            if "RELS-EXT" not in self.ds_list.keys():
                return []
            else:
                raise
            
        return list(rels.objects(self.uriref, modelns.hasModel))

    def index_data(self):
        '''Generate and return a dictionary of default fields to be
        indexed for searching (e.g., in Solr).  Includes top-level
        object properties, Content Model URIs, and Dublin Core
        fields.

        This method is intended to be customized and extended in order
        to easily modify the fields that should be indexed for any
        particular type of object in any project; data returned from
        this method should be serializable as JSON (the current
        implementation uses :mod:`django.utils.simplejson`).
        
        This method was designed for use with :mod:`eulfedora.indexdata`.
        '''
        index_data = {
            'pid': self.pid,	
            'label': self.label,
            'owner': self.owners,
            'state': self.state,
            'content_model': [str(cm) for cm in self.get_models()],	# convert URIRefs to strings
            }

        # date created/modified won't be set unless the object actually exists in Fedora
        # (probably the case for anything being indexed, except in tests)
        if self.exists:
            index_data.update({
                # last_modified and created are configured as date type in sample solr Schema
                # using isoformat here so they can be serialized via JSON
                'last_modified': self.modified.isoformat(),	
                'created': self.created.isoformat(),
                # datastream ids
                'dsids': list(self.ds_list.iterkeys()),
            })
            
        index_data.update(self.index_data_descriptive())
        index_data.update(self.index_data_relations())
        
        return index_data

    def index_data_descriptive(self):
        '''Descriptive data to be included in :meth:`index_data`
        output.  This implementation includes all Dublin Core fields,
        but should be extended or overridden as appropriate for custom
        :class:`~eulfedora.models.DigitalObject` classes.'''

        dc_fields = ['title', 'contributor', 'coverage', 'creator', 'date', 'description',
                     'format', 'identifier', 'language', 'publisher', 'relation',
                     'rights', 'source', 'subject', 'type']
        dc_data = {}
        for field in dc_fields:
            list_field = getattr(self.dc.content, '%s_list' % field)
            if list_field:
                # convert xmlmap lists to straight lists so simplejson can handle them
                dc_data[field] = list(list_field)
        return dc_data

    def index_data_relations(self):
        '''Standard Fedora relations to be included in
        :meth:`index_data` output.  This implementation includes all
        standard relations included in the Fedora relations namespace,
        but should be extended or overridden as appropriate for custom
        :class:`~eulfedora.models.DigitalObject` classes.'''
        data = {}
        # NOTE: hasModel relation is handled with top-level object properties above
        # currently not indexing other model rels (service bindings)
        for rel in fedora_rels:
            values = []
            for o in self.rels_ext.content.objects(self.uriref, relsextns[rel]):
                values.append(str(o))
            if values:
                data[rel] = values
        return data


        
class ContentModel(DigitalObject):
    """Fedora CModel object"""

    CONTENT_MODELS = ['info:fedora/fedora-system:ContentModel-3.0']
    ds_composite_model = XmlDatastream('DS-COMPOSITE-MODEL',
            'Datastream Composite Model', DsCompositeModel, defaults={
                'format': 'info:fedora/fedora-system:FedoraDSCompositeModel-1.0',
                'control_group': 'X',
                'versionable': True,
            })

    @staticmethod
    def for_class(cls, repo):
        full_name = '%s.%s' % (cls.__module__, cls.__name__)
        cmodels = getattr(cls, 'CONTENT_MODELS', None)
        if not cmodels:
            logger.debug('%s has no content models' % (full_name,))
            return None
        if len(cmodels) > 1:
            logger.debug('%s has %d content models' % (full_name, len(cmodels)))
            raise ValueError(('Cannot construct ContentModel object for ' +
                              '%s, which has %d CONTENT_MODELS (only 1 is ' +
                              'supported)') %
                             (full_name, len(cmodels)))

        cmodel_uri = cmodels[0]
        logger.debug('cmodel for %s is %s' % (full_name, cmodel_uri))
        cmodel_obj = repo.get_object(cmodel_uri, type=ContentModel,
                                     create=False)
        if cmodel_obj.exists:
            logger.debug('%s already exists' % (cmodel_uri,))
            return cmodel_obj

        # otherwise the cmodel doesn't exist. let's create it.
        logger.debug('creating %s from %s' % (cmodel_uri, full_name))
        cmodel_obj = repo.get_object(cmodel_uri, type=ContentModel,
                                     create=True)
        # XXX: should this use _defined_datastreams instead?
        for ds in cls._local_datastreams.values():
            ds_composite_model = cmodel_obj.ds_composite_model.content
            type_model = ds_composite_model.get_type_model(ds.id, create=True)
            type_model.mimetype = ds.default_mimetype
            if ds.default_format_uri:
                type_model.format_uri = ds.default_format_uri
        cmodel_obj.save()
        return cmodel_obj


class DigitalObjectSaveFailure(StandardError):
    """Custom exception class for when a save error occurs part-way through saving 
    an instance of :class:`DigitalObject`.  This exception should contain enough
    information to determine where the save failed, and whether or not any changes
    saved before the failure were successfully rolled back.

    These properties are available:
     * obj_pid - pid of the :class:`DigitalObject` instance that failed to save
     * failure - string indicating where the failure occurred (either a datastream ID or 'object profile')
     * to_be_saved - list of datastreams that were modified and should have been saved
     * saved - list of datastreams that were successfully saved before failure occurred
     * cleaned - list of saved datastreams that were successfully rolled back
     * not_cleaned - saved datastreams that were not rolled back
     * recovered - boolean, True indicates all saved datastreams were rolled back
    
    """
    def __init__(self, pid, failure, to_be_saved, saved, cleaned):
        self.obj_pid = pid
        self.failure = failure
        self.to_be_saved = to_be_saved
        self.saved = saved
        self.cleaned = cleaned
        # check for anything was saved before failure occurred that was *not* cleaned up
        self.not_cleaned = [item for item in self.saved if not item in self.cleaned]
        self.recovered = (len(self.not_cleaned) == 0)

    def __str__(self):
        return "Error saving %s - failed to save %s; saved %s; successfully backed out %s" \
                % (self.obj_pid, self.failure, ', '.join(self.saved), ', '.join(self.cleaned))

### Descriptors for dealing with object relations

# Relation
# ReverseRelation 
# single/multiple variants  (TODO)

class Relation(object):
    '''Descriptor for use with
    :class:`~eulfedora.models.DigitalObject` RELS-EXT relations.
    Allows getting, setting, and removing related DigitalObjects and
    literals in the RELS-EXT of the object.
    
    Example use for a related object.  The Relation should be defined
    something like this, passing in the predicate URI and optionally
    the subclass of :class:`~eulfedora.models.DigitalObject` that
    should be returned::

    	class Page(DigitalObject):
            volume = Relation(relsext.isConstituentOf, type=Volume)


    :class:`~eulfedora.models.Relation` also supports configuring the
    RDF type and namespace prefixes that should be used for
    serialization; for example::
        
        from rdflib import XSD, URIRef
        from rdflib.namespace import Namespace
        
        MYNS = Namespace(URIRef("http://example.com/ns/2011/my-test-namespace/#"))

        int = Relation(MYNS.count, ns_prefix={"my": MYNS}, rdf_type=XSD.int)


    Initialization options:

    :param relation: the RDF predicate URI
    :param type: optional :class:`~eulfedora.models.DigitalObject` subclass
    	to initialize (for object relations)
    :param ns_prefix: optional dictionary to configure namespace
    	prefixes to be used for serialization; key should be the
        desired prefix, value should be an instance of
        :class:`rdflib.namespace.Namespace`
    :param rdf_type: optional rdf type for literal values (passed
        to :class:`rdflib.Literal` as the datatype option)
    '''
    
    def __init__(self, relation, type=None, ns_prefix={}, rdf_type=None):
        self.relation = relation
        self.object_type = type
        self.ns_prefix = ns_prefix
        self.rdf_type = rdf_type

    def __get__(self, obj, objtype):
        # no caching on related objects for now
        uri_val = obj.rels_ext.content.value(subject=obj.uriref,
                                         predicate=self.relation)
        if uri_val and self.object_type:	# don't init new object if val is None
            # need get_object wrapper method on digital object
            return obj.get_object(uri_val, type=self.object_type)
        else:
            return uri_val

    def __set__(self, obj, subject):
        # if any namespace prefixes were specified, bind them before adding the tuple
        for prefix, ns in self.ns_prefix.iteritems():
            obj.rels_ext.content.bind(prefix, ns)

        # TODO: do we need to check that subject matches self.object_type (if any)?

        if isinstance(subject, URIRef):
            subject_uri = subject
        elif hasattr(subject, 'uriref'):
            subject_uri = subject.uriref
        elif self.rdf_type:
            subject_uri = Literal(subject, datatype=self.rdf_type)
        else:
            subject_uri = Literal(subject)
        
        # set the property in the rels-ext, removing any existing
        # value for that property (single-value relation only, for now)
        obj.rels_ext.content.set((
            obj.uriref,
            self.relation,
            subject_uri
        ))

    def __delete__(self, obj):
        # find the subject uri and remove from rels-ext
        uris = list(obj.rels_ext.content.objects(obj.uriref, self.relation))
        if uris:
            obj.rels_ext.content.remove((
                obj.uriref,
                self.relation,
                uris[0]
            ))


class ReverseRelation(object):
    '''Descriptor for use with
    :class:`~eulfedora.models.DigitalObject` RELS-EXT reverse
    relations, where the owning object is the RDF **object** of the
    predicate and the related object is the RDF **subject**.  This
    descriptor will query the Fedora
    :class:`~eulfedora.api.ResourceIndex` for the requested subjects,
    based on the configured predicate, and return resulting items.

    Currently only supports get (no set or delete).
    
    .. Note::
    
       Currently has no support for sorting when multiple items are
       returned; items will be returned in whatever order the
       :class:`~eulfedora.api.ResourceIndex` returns them.
    
    Example use::

    	class Volume(DigitalObject):
            pages = ReverseRelation(relsext.isConstituentOf, type=Page, multiple=True)
            
    '''
    def __init__(self, relation, type=None, multiple=False):
        self.relation = relation
        self.object_type = type
        self.multiple = multiple

    def __get__(self, obj, objtype):
        # query RIsearch for subjects based on configured relation and current object
        uris = list(obj.risearch.get_subjects(self.relation, obj.uriref))
        if uris:
            if self.multiple:
                return [self._init_val(obj, uri) for uri in uris]
            else:
                return self._init_val(obj, uris[0])

    def _init_val(self, obj, val):
        # initialize the desired return type, based on configuration
        # would any reverse relation not be an object?
        if self.object_type:
            return obj.get_object(val, type=self.object_type)
        else:
            return val
