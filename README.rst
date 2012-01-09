README
======

EULfedora is a `Python <http://www.python.org/>`_ module that provides
utilities, API wrappers, and classes for interacting with the
`Fedora-Commons Repository <http://fedora-commons.org/>`_ (version
3.4.x) in a pythonic, object-oriented way, with optional `Django
<https://www.djangoproject.com/>`_ integration.

**eulfedora.api** provides complete access to the Fedora API,
primarily making use of Fedora's 
`REST API <https://wiki.duraspace.org/display/FCR30/REST+API>`_.  This
low-level interface is wrapped by **eulfedora.server.Repository** and
**eulfedora.models.DigitalObject**, which provide a more abstract,
object-oriented, and Pythonic way of interacting with a Fedora
Repository or with individual objects and datastreams.

**eulfedora.indexdata** provides a webservice that returns data for
fedora objects in JSON form, which can be used in conjunction with a
service for updating an index, such as `eulindexer`.

When used with `Django <https://www.djangoproject.com/>`_,
**eulfedora** can pull the Repository connection configuration from
Django settings, and provides a custom management command for loading
simple content models and fixture objects to the configured
repository.


Dependencies
------------

**eulfedora** currently depends on 
`eulxml <https://github.com/emory-libraries/eulxml>`_,
`rdflib <http://www.rdflib.net/>`_,
`python-dateutil <http://labix.org/python-dateutil>`_,
`pycrypto <https://www.dlitz.net/software/pycrypto/>`_,
`soaplib <http://pypi.python.org/pypi/soaplib/0.8.1>`_.

**eulfedora** can be used without 
`Django <https://www.djangoproject.com/>`_, but additional
functionality is available when used with Django.


Contact Information
-------------------

**eulfedora** was created by the Digital Programs and Systems Software
Team of `Emory University Libraries <http://web.library.emory.edu/>`_.

libsysdev-l@listserv.cc.emory.edu


License
-------
**eulfedora** is distributed under the Apache 2.0 License.


Development History
-------------------

For instructions on how to see and interact with the full development
history of **eulfedora**, see
`eulcore-history <https://github.com/emory-libraries/eulcore-history>`_.


Developer Notes
---------------
When running unit tests you must set the the PYTHONPATH variable::

    $ PYTHONPATH = .:test
