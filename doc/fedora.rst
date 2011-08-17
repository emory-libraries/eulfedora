:mod:`eulfedora` -- Python objects to interact with the Fedora Commons repository
==================================================================================

.. module:: eulfedora

.. toctree::
   :maxdepth: 1

   Object and Datastream Models <fedora/models>
   API XML Objects <fedora/xml>


Server objects
---------------

Repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: eulfedora.server
   
.. autoclass:: Repository
    :members:


Resource Index
^^^^^^^^^^^^^^

.. autoclass:: eulfedora.api.ResourceIndex
    :members:


Django integration
------------------

:mod:`~eulfedora.views` Fedora views
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: eulfedora.views

   .. automethod:: eulfedora.views.raw_datastream


:mod:`~eulfedora.indexdata` Fedora Indexing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: eulfedora.indexdata

  .. automodule:: eulfedora.indexdata.views
    :members:
  

Management commands
^^^^^^^^^^^^^^^^^^^

The following management commands will be available when you include
:mod:`eulfedora` in your django ``INSTALLED_APPS`` and rely on the
existdb settings described above.

For more details on these commands, use ``manage.py <command> help``

 * **syncrepo** - load simple content models and fixture object to the
   configured fedora repository

:mod:`~eulfedora` Template tags
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. module:: eulfedora.templatetags

:mod:`eulfedora` adds custom `template tags
<http://docs.djangoproject.com/en/1.2/topics/templates/#custom-tag-and-filter-libraries>`_
for use in templates.

fedora_access
~~~~~~~~~~~~~

Catch fedora failures and permission errors encountered during template
rendering::

   {% load fedora %}

   {% fedora_access %}
      <p>Try to access data on fedora objects which could be
        <span class='{{ obj.inaccessible_ds.content.field }}'>inaccessible</span>
        or when fedora is
        <span class='{{ obj.regular_ds.content.other_field }}'>down</span>.</p>
   {% permission_denied %}
      <p>Fall back to this content if the main body results in a permission
        error while trying to access fedora data.</p>
   {% fedora_failed %}
      <p>Fall back to this content if the main body runs into another error
        while trying to access fedora data.</p>
   {% end_fedora_access %}

The ``permission_denied`` and ``fedora_failed`` sections are optional. If
only ``permission_denied`` is present then non-permission errors will result
in the entire block rendering empty. If only ``fedora_failed`` is present
then that section will be used for all errors whether permission-related or
not. If neither is present then all errors will result in the entire block
rendering empty.

Note that when Django's ``TEMPLATE_DEBUG`` setting is on, it precludes all
error handling and displays the Django exception screen for all errors,
including fedora errors, even if you use this template tag. To disable this
Django internal functionality and see the effects of the ``fedora_access``
tag, add the following to your Django settings::

   TEMPLATE_DEBUG = False


:mod:`~eulfedora.testutil` Unittest utilities
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: eulfedora.testutil
   :members:

