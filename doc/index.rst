EULfedora
=========

EULfedora is an extensible library for creating and managing digital objects
in a `Fedora Commons <http://fedora-commons.org/>`_ repository. It eases
`mapping Fedora digital object types to Python classes
<tutorials/fedora.html#create-a-model-for-your-fedora-object>`_ along with
`ingesting <tutorials/fedora.html#process-the-upload>`_, `managing
<tutorials/fedora.html#edit-fedora-content>`_, and `searching
<tutorials/fedora.html#search-fedora-content>`_ reposited content. Its
builtin datastream abstractions include idiomatic Python access to `XML
<fedora/models.html#eulfedora.models.XmlDatastream>`_ and `RDF
<fedora/models.html#eulfedora.models.RdfDatastream>`_ datastreams. They're
also extensible, allowing applications to define other datastream types as
needed.

The library contains extra `integration for Django apps
<fedora.html#django-integration>`_, though the core repository functionality
is framework-agnostic.

Contents
--------

.. toctree::
   :maxdepth: 2
   
   tutorials/fedora
   tutorials/examples
   fedora
   changelog
   readme

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
