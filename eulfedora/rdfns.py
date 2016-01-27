# file eulfedora/rdfns.py
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


'''
Predefined RDF namespaces for convenience, for use with
:class:`~eulfedora.models.RdfDatastream` objects, in
:class:`~eulfedora.api.ResourceIndex` queries, for defining a
:class:`eulfedora.models.Relation`, for adding relationships via
:meth:`eulfedora.models.DigitalObject.add_relationship`, or anywhere
else that Fedora-related :class:`rdflib.term.URIRef` objects might
come in handy.

Example usage::

  from eulfedora.models import DigitalObject, Relation
  from eulfedora.rdfns import relsext as relsextns

  class Item(DigitalObject):
    collection = Relation(relsextns.isMemberOfCollection)

----
'''

from __future__ import unicode_literals
from rdflib import URIRef
from rdflib.namespace import ClosedNamespace

# ids copied from http://www.fedora.info/definitions/1/0/fedora-relsext-ontology.rdfs
fedora_rels = [
    'fedoraRelationship',
    'isPartOf',
    'hasPart',
    'isConstituentOf',
    'hasConstituent',
    'isMemberOf',
    'hasMember',
    'isSubsetOf',
    'hasSubset',
    'isMemberOfCollection',
    'hasCollectionMember',
    'isDerivationOf',
    'hasDerivation',
    'isDependentOf',
    'hasDependent',
    'isDescriptionOf',
    'HasDescription',
    'isMetadataFor',
    'HasMetadata',
    'isAnnotationOf',
    'HasAnnotation',
    'hasEquivalent',
]


relsext = ClosedNamespace('info:fedora/fedora-system:def/relations-external#',
                          fedora_rels)
''':class:`rdflib.namespace.ClosedNamespace` for the `Fedora external
relations ontology
<http://www.fedora.info/definitions/1/0/fedora-relsext-ontology.rdfs>`_.
'''

# TODO: find and catalog full namespace. currently this is just a list of
# names we use in this ns.
model = ClosedNamespace('info:fedora/fedora-system:def/model#', [
    'hasModel',
])
''':class:`rdflib.namespace.ClosedNamespace` for the Fedora model
namespace (currently only includes ``hasModel``).'''



# these are the OAI terms used with the PROAI OAI provider commonly used with Fedora
# (terms not actually defined at the namespace specified...)
oai = ClosedNamespace(
    uri = URIRef("http://www.openarchives.org/OAI/2.0/"),
    terms = [
        "itemID", "setSpec", "setName"
        ]
    )
''':class:`rdflib.namespace.ClosedNamespace` for the OAI relations
commonly used with Fedora and the PROAI OAI provider.  Available URIs
are: ``itemID``, ``setSpec``, and ``setName``.'''
