Example Uses
============

Bulk purging test objects via console
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The combination of :mod:`eulfedora` and interactive Python or Django's
shell provides a simple but powerful console interface to Fedora.  For
example, if you loaded a bunch of test or demo objects to a test or
development Fedora instance and you wanted to remove them, you could
purge them with :mod:`eulfedora` as follows.  This example assumes a
django project with Fedora settings configured and :mod:`eulfedora`
already installed (see :mod:`eulfedora.server` for documentation on
supported Django settings).  First, start up the Django console::

    $ python manage.py shell

Inside the Django shell, import :class:`~eulfedora.server.Repository`
and your Django settings to easily initialize a Repository connection
to your configured Fedora (in this example, we're accessing the
repository that is configured for testing)::

    >>> from eulfedora.server import Repository
    >>> from django.conf import settings
    >>> repo = Repository(settings.FEDORA_TEST_ROOT, \
    ...    settings.FEDORA_TEST_USER, settings.FEDORA_TEST_PASSWORD)
    >>> for o in repo.find_objects(pid__contains='test-obj:*'):
    ...     repo.purge_object(o.pid)
    ...         

This example will find and purge all objects in the ``test-obj``
pidspace.  Of course, you could easily find objects by ownerId, title
text, or any of the other fields supported by
:meth:`~eulfedora.server.Repository.find_objects`.

.. note:

  This example uses Django settings and shell for convenience, but the
  same thing would work pretty simply in a standard Python shell.


