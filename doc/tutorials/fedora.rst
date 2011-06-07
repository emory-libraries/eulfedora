Creating a simple Django app for Fedora Commons repository content
==================================================================

This is a tutorial to walk you through using EULfedora with Django to build
a simple interface to the Fedora-Commons repository for uploading files,
viewing uploaded files in the repository, editing Dublin Core metadata,
and searching content in the repository.

This tutorial assumes that you have an installation of the `Fedora Commons
repository`_ available to interact with.  You should have some familiarity with
Python and Django (at the very least, you should have worked through the
`Django Tutorial`_). You should also have some familiarity with the Fedora
Commons Repository and a basic understanding of objects and content models in
Fedora.

.. _Django Tutorial: http://docs.djangoproject.com/en/1.2/intro/tutorial01/
.. _Fedora Commons repository: http://www.fedora-commons.org/

We will use `pip <http://www.pip-installer.org/en/latest/index.html>`_ to
install EULfedora and its dependencies; on some platforms (most notably, in
Windows), you may need to install some of the python dependencies manually.


Create a new Django project and setup :mod:`eulfedora`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use ``pip`` to install the :mod:`eulfedora` library and its
dependencies.  For this tutorial, we'll use the latest released
version::

    $ pip install eulfedora

This command should install EULfedora and its Python dependencies.

We're going to make use of a few items in :mod:`eulcommon`, so let's
install that now too::

    $ pip install eulcommon

We'll use `Django <http://www.djangoproject.org/>`_, a popular web framework,
for the web components of this tutorial::

    $ pip install django
    
Now, let's go ahead and create a new Django project.  We'll call it
*simplerepo*::

    $ django-admin.py startproject simplerepo

Go ahead and do some minimal configuration in your django settings.
For simplicity, you can use a sqlite database for this tutorial (in
fact, we won't make much use of this database).

In addition to the standard Django settings, add :mod:`eulfedora` to
your ``INSTALLED_APPS`` and add Fedora connection configurations to
your ``settings.py`` so that the :mod:`eulfedora`
:class:`~eulfedora.server.Repository` object can automatically connect
to your configured Fedora repository::

    # Fedora Repository settings
    FEDORA_ROOT = 'https://localhost:8543/fedora/'
    FEDORA_USER = 'fedoraAdmin'
    FEDORA_PASSWORD = 'fedoraAdmin'
    FEDORA_PIDSPACE = 'simplerepo'

Since we're planning to upload content into Fedora, make sure you are
using a fedora user account that has permission to upload, ingest, and
modify content.

Create a model for your Fedora object
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before we can upload any content, we need to create an object to
represent how we want to store that data in Fedora.  Let's create a
new Django app where we will create this model and associated views::

    $ python manage.py startapp repo

In ``repo/models.py``, create a class that extends :class:`~eulfedora.models.DigitalObject`::

    from eulfedora.models import DigitalObject, FileDatastream

    class FileObject(DigitalObject):
        FILE_CONTENT_MODEL = 'info:fedora/genrepo:File-1.0'
        CONTENT_MODELS = [ FILE_CONTENT_MODEL ]
        file = FileDatastream("FILE", "Binary datastream", defaults={
                'versionable': True,
        })

What we're doing here extending the default
:class:`~eulfedora.models.DigitalObject`, which gives us Dublin Core
and RELS-EXT datastream mappings for free, since those are part of
every Fedora object.  In addition, we're defining a custom datastream
that we will use to store the binary files that we're going to upload
for ingest into Fedora.  This configures a versionable
:class:`~eulfedora.models.FileDatastream` with a datastream id of
``FILE`` and a default datastream label of ``Binary datastream``.  We
could also set a default mimetype here, if we wanted.

Let's inspect our new model object in the Django console for a moment::

    $ python manage.py shell

The easiest way to initialize a new object is to use the Repository object ``get_object`` method, which can also be used
to access existing Fedora objects.  Using the Repository object allows us to seamlessly pass along the Fedora
connection configuration that the Repository object picks up from your django ``settings.py``::

    >>> from eulfedora.server import Repository
    >>> from simplerepo.repo.models import FileObject

    # initialize a connection to the configured Fedora repository instance
    >>> repo = Repository()

    # create a new FileObject instance
    >>> obj = repo.get_object(type=FileObject)
    # this is an uningested object; it will get the default type of generated pid when we save it
    >>> obj
    <FileObject (generated pid; uningested)>

    # every DigitalObject has Dublin Core
    >>> obj.dc
    <eulfedora.models.XmlDatastreamObject object at 0xa56f4ec>
    # dc.content is where you access and update the actual content of the datastream
    >>> obj.dc.content
    <eulxml.xmlmap.dc.DublinCore object at 0xa5681ec>
    # print out the content of the DC datastream - nothing there (yet)
    >>> print obj.dc.content.serialize(pretty=True)
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/"/>

    # every DigitalObject also gets rels_ext for free
    >>> obj.rels_ext
    <eulfedora.models.RdfDatastreamObject object at 0xa56866c>
    # this is an RDF datastream, so the content uses rdflib instead of :mod:`eulxml.xmlmap`
    >>> obj.rels_ext.content
    <Graph identifier=omYiNhtw0 (<class 'rdflib.graph.Graph'>)>
    # print out the content of the rels_ext datastream
    # notice that it has a content-model relation defined based on our class definition
    >>> print obj.rels_ext.content.serialize(pretty=True)
    <?xml version="1.0" encoding="UTF-8"?>
    <rdf:RDF
       xmlns:fedora-model="info:fedora/fedora-system:def/model#"
       xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    >
      <rdf:Description rdf:about="info:fedora/TEMP:DUMMY_PID">
        <fedora-model:hasModel rdf:resource="info:fedora/genrepo:File-1.0"/>
      </rdf:Description>
    </rdf:RDF>

    # our FileObject also has a custom file datastream, but there's no content yet
    >>> obj.file
    <eulfedora.models.FileDatastreamObject object at 0xa56ffac>

    # save the object to Fedora
    >>> obj.save()

    # our object now has a pid that was automatically generated by Fedora
    >>> obj.pid
    'simplerepo:1'
    # the object also has information about when it was created, modified, etc
    >>> obj.created
    datetime.datetime(2011, 3, 16, 19, 22, 46, 317000, tzinfo=tzutc())
    >>> print obj.created
    2011-03-16 19:22:46.317000+00:00
    # datastreams have this kind of information as well
    >>> print obj.dc.mimetype
    text/xml
    >>> print obj.dc.created
    2011-03-16 19:22:46.384000+00:00

    # we can modify the content and save the changes
    >>> obj.dc.content.title = 'My SimpleRepo test object'
    >>> obj.save()

We've defined a FileObject with a custom content model, but we haven't
created the content model object in Fedora yet.  For simple content
models, we can do this with a custom django manage.py command.  Run it
in verbose mode so you can more details about what it is doing::

    $ python manage.py syncrepo -v 2


You should see some output indicating that content models were
generated for the class you just defined.

This command was is analogous to the Django ``syncdb`` command.  It
looks through your models for classes that extend DigitalObject, and
when it finds content models defined that it can generate, which don't
already exist in the configured repository, it will generate them and
ingest them into Fedora.  It can also be used to load initial objects
by way of simple XML filters.


Create a view to upload content
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

So, we have a custom :class:`~eulfedora.models.DigitalObject` defined.
Let's do something with it now.

Display an upload form
----------------------

We haven't defined any url patterns yet, so let's create a ``urls.py``
for our repo app and hook that into the main project urls.  Create
``repo/urls.py`` with this content::

    from django.conf.urls.defaults import *

    urlpatterns = patterns('simplerepo.repo.views',
        url(r'^upload/$', 'upload', name='upload'),
    )

Then include that in your project ``urls.py``::

    (r'^', include('simplerepo.repo.urls')),

Now, let's define a simple upload form and a view method to correspond
to that url.  First, for the form, create a file named
``repo/forms.py`` and add the following::

    from django import forms

    class UploadForm(forms.Form):
        label = forms.CharField(max_length=255, # fedora label maxes out at 255 characters
                    help_text='Preliminary title for the new object. 255 characters max.')
        file = forms.FileField()

The minimum we need to create a new FileObject in Fedora is a file to
ingest and a label for the object in Fedora.  We're could actually
make the label optional here, because we could use the file name as a
preliminary label, but for simplicity let's require it.

Now, define an upload view to use this form.  For now, we're just
going to display the form on GET; we'll add the form processing in a
moment.  Edit ``repo/views.py`` and add::

    from django.shortcuts import render_to_response
    from django.template import RequestContext
    from simplerepo.repo.forms import UploadForm

    def upload(request):
        if request.method == 'GET':
               form = UploadForm()

        return render_to_response('repo/upload.html', 
               {'form': form}, context_instance=RequestContext(request))

But we still need a template to display our form.  Create a template
directory and add it to your ``TEMPLATE_DIRS`` configuration in
``settings.py``.  Create a ``repo`` directory inside your template
directory, and then create ``upload.html`` inside that directory and
give it this content:

.. code-block:: django

    <form method="post" enctype="multipart/form-data">{% csrf_token %}
        {{ form.as_p }}
        <input type="submit" value="Submit"/>
    </form>

Let's start the django server and make sure everything is working so
far.  Start the server::

    $ python manage.py runserver

Then load `<http://localhost:8000/upload/>`_ in your Web browser.  You
should see a simple upload form with the two fields defined.

Process the upload
------------------

Ok, but our view doesn't do anything yet when you submit the web form.
Let's add some logic to process the form.  We need to import the
Repository and FileObject classes and use the posted form data to
initialize and save a new object, rather like what we did earlier when
we were investigating FileObject in the console.  Modify your
``repo/views.py`` so it looks like this::

    from django.shortcuts import render_to_response
    from django.template import RequestContext
    
    from eulfedora.server import Repository

    from simplerepo.repo.forms import UploadForm
    from simplerepo.repo.models import FileObject

    def upload(request):
        obj = None
        if request.method == 'POST':
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                # initialize a connection to the repository and create a new FileObject
                repo = Repository()
                obj = repo.get_object(type=FileObject)
                # set the file datastream content to use the django UploadedFile object
                obj.file.content = request.FILES['file']
                # use the browser-supplied mimetype for now, even though we know this is unreliable
                obj.file.mimetype = request.FILES['file'].content_type
                # let's store the original file name as the datastream label
                obj.file.label = request.FILES['file'].name
                # set the initial object label from the form as the object label and the dc:title
                obj.label = form.cleaned_data['label']
                obj.dc.content.title = form.cleaned_data['label']
                obj.save()

                # re-init an empty upload form for additional uploads
                form = UploadForm()

        elif request.method == 'GET':
               form = UploadForm()

        return render_to_response('repo/upload.html', {'form': form, 'obj': obj},
            context_instance=RequestContext(request))

When content is posted to this view, we're binding our form to the
request data and, when the form is valid, creating a new FileObject
and initializing it with the label and file that were posted, and
saving it.  The view is now passing that object to the template, so if
it is defined that should mean we've successfully ingested content
into Fedora.  Let's update our template to show something if that is
defined.  Add this to ``repo/upload.html`` before the form is
displayed:

.. code-block:: django

    {% if obj %}
        <p>Successfully ingested <b>{{ obj.label }}</b> as {{ obj.pid }}.</p>
        <hr/>
        {# re-display the form to allow additional uploads #}
        <p>Upload another file?</p>
    {% endif %}

Go back to the upload page in your web browser.  Go ahead and enter a
label, select a file, and submit the form.  If all goes well, you
should see a the message we added to the template for successful
ingest, along with the pid of the object you just created.

.. TODO: error handling (e.g., permission denied on ingest)

Display uploaded content
^^^^^^^^^^^^^^^^^^^^^^^^

Now we have a way to get content in Fedora, but we don't have any way
to get it back out.  Let's build a display method that will allow us
to view the object and its metadata.

Object display view
-------------------

Add a new url for a single-object view to your urlpatterns in
``repo/urls.py``::

    url(r'^objects/(?P<pid>[^/]+)/$', 'display', name='display'),

Then define a simple view method that takes a pid in
``repo/views.py``::

    def display(request, pid):
        repo = Repository()
        obj = repo.get_object(pid, type=FileObject)
        return render_to_response('repo/display.html', {'obj': obj})

For now, we're going to assume the object is the type of object we
expect and that we have permission to access it in Fedora; we can add
error handling for those cases a bit later.

We still need a template to display something.  Create a new file
called ``repo/display.html`` in your templates directory, and then add
some code to output some information from the object:

.. code-block:: django

    <h1>{{ obj.label }}</h1>
    <table>
        <tr><th>pid:</th><td> {{ obj.pid }}</td></tr>
        {% with obj.dc.content as dc %}
            <tr><th>title:</th><td>{{ dc.title }}</td></tr>
            <tr><th>creator:</th><td>{{ dc.creator }}</td></tr>
            <tr><th>date:</th><td>{{ dc.date }}</td></tr>
     {% endwith %}
    </table>

We're just using a simple table layout for now, but of course you can
display this object information anyway you like.  We're just starting
with a few of the Dublin Core fields for now, since most of them don't
have any content yet.

Go ahead and take a look at the object you created before using the
upload form.  If you used the ``simplerepo`` PIDSPACE configured
above, then the the first item you uploaded should now be viewable at
`<http://localhost:8000/objects/simplerepo:1/>`_.

You might notice that we're displaying the text 'None' for creator and
date.  This is because those fields aren't present at all yet in our
object Dublin Core, and :mod:`eulxml.xmlmap` fields distinguish
between an empty XML field and one that is not-present at all by using
the empty string and None respectively.  Still, that doesn't look
great, so let's adjust our template a little bit:

.. code-block:: django

    <tr><th>creator:</th><td>{{ dc.creator|default:'' }}</td></tr>
    <tr><th>date:</th><td>{{ dc.date|default:'' }}</td></tr>

We actually have more information about this object than we're currently
displaying, so let's add a few more things to our object display template.
The object has information about when it was created and when it was last
modified, so let's add a line after the object label:

.. code-block:: django

    <p>Uploaded at {{ obj.created }}; last modified {{ obj.modified }}.</p>

These fields are actually Python datetime objects, so we can use
Django template filters to display then a bit more nicely.  Try
modifying the line we just added:

.. code-block:: django

    <p>Uploaded at {{ obj.created }}; last modified {{ obj.modified }}
       ({{  obj.modified|timesince }} ago).</p>

It's pretty easy to display the Dublin Core datastream content as XML
too.  This may not be something you'd want to expose to regular users,
but it may be helpful as we develop the site.  Add a few more lines at
the end of your ``repo/display.html`` template:

.. code-block:: django

    <hr/>
    <pre>{{ obj.dc.content.serialize }}</pre>

You could do this with the RELS-EXT just as easily (or basically any
XML or RDF datastream), although it may not be as valuable for now,
since we're not going to be modifying the RELS-EXST just yet.

So far, we've got information about the object and the Dublin Core
displaying, but nothing about the file that we uploaded to create this
object.  Let's add a bit more to our template:

.. code-block:: django

    <p>{{ obj.file.label }} ({{ obj.file.info.size|filesizeformat }},
                             {{ obj.file.mimetype }})</p>

Remember that in our ``upload`` view method we set the file datastream
label and mimetype based on the file that was uploaded from the web
form.  Those are stored in Fedora as part of the datastream
information, along with some other things that Fedora calculates for
us, like the size of the content.


Download File datastream
------------------------

Now we're displaying information about the file, but we don't actually
have a way to get the file back out of Fedora yet.  Let's add another
view.

Add another line to your url patterns in ``repo/urls.py``::

    url(r'^objects/(?P<pid>[^/]+)/file/$', 'file', name='download'),

And then update ``repo/views.py`` to define the new view method.
First, we need to add a new import::

    from eulfedora.views import raw_datastream

:meth:`eulfedora.views.raw_datastream` is a generic view method that
can be used for displaying datastream content from fedora objects.  In
some cases you may be able to use
:meth:`~eulfedora.views.raw_datastream` directly (e.g., it might be
useful for displaying XML datastreams), but in this case we want to
add an extra header to indicate that the content should be downloaded.
Add this method to ``repo/views.py``::

    def file(request, pid):
        dsid = 'FILE'
        extra_headers = {
            'Content-Disposition': "attachment; filename=%s.pdf" % pid,
        }
        return raw_datastream(request, pid, dsid, type=FileObject, headers=extra_headers)

We've defined a content disposition header so the user will be
prompted to save the response with a filename based on the pid do the
object in fedora.  The :meth:`~eulfedora.views.raw_datastream` method
will add a few additional response headers based on the datastream
information from Fedora.  Let's link this in from our object display
page so we can try it out.  Edit your ``repo/display.html`` template
and turn the original filename into a link:

.. code-block:: django

	<a href="{% url download obj.pid %}">{{ obj.file.label }}</a> 

Now, try it out!  You should be able to download the file you
originally uploaded.

But, hang on-- you may have noticed, there are a couple of details
hard-coded in our download view that really shouldn't be.  What if the
file you uploaded wasn't a PDF?  What if we decide we want to use a
different datastream ID?  Let's revise our view method a bit::

    def file(request, pid):
        dsid = FileObject.file.id
        repo = Repository()
        obj = repo.get_object(pid, type=FileObject)
        extra_headers = {
            'Content-Disposition': "attachment; filename=%s" % obj.file.label,
        }
        return raw_datastream(request, pid, dsid, type=FileObject, headers=extra_headers)

We can get the ID for the file datastream directly from the
:class:`~eulfedora.models.FileDatastream` object on our
FileObject class.  And in our upload view we set the original file
name as our datastream label, so we'll go ahead and use that as the
download name.

.. TODO: error handling (404, permission)

Edit Fedora content
^^^^^^^^^^^^^^^^^^^

So far, we can get content into Fedora and we can get it back out.
Now, how do we modify it?  Let's build an edit form & a view that we
can use to update the Dublin Core metadata.

XmlObjectForm for Dublin Core
-----------------------------

We're going to create an :class:`eulxml.forms.XmlObjectForm` instance
for editing :class:`eulxml.xmlmap.dc.DublinCore`.
:class:`~eulxml.forms.XmlObjectForm` is roughly analogous to Django's
:class:`~django.forms.ModelForm`, except in place of a Django Model we
have an :class:`~eulxml.xmlmap.XmlObject` that we want to make
editable.

First, add some new imports to ``repo/forms.py``::

    from eulxml.xmlmap.dc import DublinCore
    from eulxml.forms import XmlObjectForm

Then we can define our new edit form::

    class DublinCoreEditForm(XmlObjectForm):
        class Meta:
            model = DublinCore
            fields = ['title', 'creator', 'date']

We'll start simple, with just the three fields we're currently displaying on
our object display page.  This code creates a custom
:class:`~eulxml.forms.XmlObjectForm` with a *model* of (which for us is an
instance of :class:`~eulxml.xmlmap.XmlObject`)
:class:`~eulxml.xmlmap.dc.DublinCore`.  :class:`~eulxml.forms.XmlObjectForm`
knows how to look at the model object and figure out how to generate form
fields that correspond to the xml fields. By adding a list of fields, we
tell XmlObjectForm to only build form fields for these attributes of our
model.

Now we need a view and a template to display our new form.  Add
another url to ``repo/urls.py``::

    url(r'^objects/(?P<pid>[^/]+)/edit/$', 'edit', name='edit'),

And then define the corresponding method in ``repo/views.py``.  We
need to import our new form::

	from simplerepo.repo.forms import DublinCoreEditForm

Then, use it in a view method. For now, we'll just instantiate the
form, bind it to our content, and pass it to a template::

    def edit(request, pid):
        repo = Repository()
        obj = repo.get_object(pid, type=FileObject)
        form = DublinCoreEditForm(instance=obj.dc.content)
        return render_to_response('repo/edit.html', {'form': form, 'obj': obj},
                context_instance=RequestContext(request))

We have to instantiate our object, and then pass in the *content* of
the DC datastream as the instance to our model.  Our XmlObjectForm is
using :class:`~eulxml.xmlmap.dc.DublinCore` as its model, and
``obj.dc.content`` is an instance of DublinCore with data loaded from
Fedora.

Create a new file called ``repo/edit.html`` in your templates
directory and add a little bit of code to display the form:

.. code-block:: django

    <h1>Edit {{ obj.label }}</h1>
    <form method="post">{% csrf_token %}
        <table>{{ form.as_table }}</table>
        <input type="submit" value="Save"/>
    </form>

Load the edit page for that first item you uploaded:
`<http://localhost:8000/objects/simplerepo:1/edit/>`_.  You should see
a form with the three fields that we listed.  Let's modify our view
method so it will do something when we submit the form::

    def edit(request, pid):
        repo = Repository()
        obj = repo.get_object(pid, type=FileObject)
        if request.method == 'POST':
            form = DublinCoreEditForm(request.POST, instance=obj.dc.content)
            if form.is_valid():
                form.update_instance()
                obj.save()
        elif request.method == 'GET':
            form = DublinCoreEditForm(instance=obj.dc.content)
        return render_to_response('repo/edit.html', {'form': form, 'obj': obj},
                context_instance=RequestContext(request))
	    
When the data is posted to this view, we're binding our form to the posted
data and the XmlObject instance.  If it's valid, then we can call the
:meth:`~eulxml.forms.XmlObjectForm.update_instance` method, which actually
updates the :class:`~eulxml.xmlmap.XmlObject` that is attached to our DC
datastream object based on the form data that was posted to the view. When
we save the object, the :class:`~eulfedora.models.DigitalObject` class
detects that the ``dc.content`` has been modified and will make the
necessary API calls to update that content in Fedora.

.. Note::

  It may not matter too much in this case, since we are working with simple
  Dublin Core XML, but it's probably worth noting that the form
  :meth:`~eulxml.forms.XmlObjectForm.is_valid` check actually includes `XML
  Schema <http://www.w3.org/XML/Schema>`_ validation on
  :class:`~eulxml.xmlmap.XmlObject` instances that have a schema defined.
  In most cases, it should be difficult (if not impossible) to generate
  invalid XML via an :class:`~eulxml.forms.XmlObjectForm`; but if you edit
  the XML manually and introduce something that is not schema-valid, you'll
  see the validation error when you attempt to update that content with
  :class:`~eulxml.forms.XmlObjectForm`.

Try entering some text in your form and submitting the data.  It
should update your object in Fedora with the changes you made.
However, our interface isn't very user friendly right now.  Let's
adjust the edit view to redirect the user to the object display after
changes are saved.

We'll need some additional imports::

    from django.core.urlresolvers import reverse
    from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect

.. Note::

  :class:`~eulcommon.djangoextras.http.HttpResponseSeeOtherRedirect` is a
  custom subclass of :class:`django.http.HttpResponse` analogous to
  :class:`~django.http.HttpResponseRedirect` or
  :class:`~django.http.HttpResponsePermanentRedirect`, but it returns a
  `See Other <http://tools.ietf.org/html/rfc2616#section-10.3.4>`_
  redirect (HTTP status code 303).

After the ``object.save()`` call in the edit view method, add this::

    return HttpResponseSeeOtherRedirect(reverse('display', args=[obj.pid]))

Now when you make changes to the Dublin Core fields and submit the
form, it should redirect you to the object display page and show the
changes you just made.

Right now our edit form only has three fields.  Let's customize it a
bit more.  First, let's add all of the Dublin Core fields.  Replace
the original list of fields in DublinCoreEditForm with this::

    fields = ['title', 'creator', 'contributor', 'date', 'subject',
        'description', 'relation', 'coverage', 'source', 'publisher',
        'rights', 'language', 'type', 'format', 'identifier']

Right now all of those are getting displayed as text inputs, but we
might want to treat some of them a bit differently.  Let's customize
some of the widgets::

    widgets = {
        'description': forms.Textarea,
        'date': SelectDateWidget,
    }

You'll also need to add another import line so you can use
:class:`~django.forms.extras.widgets.SelectDateWidget`::

    from django.forms.extras.widgets import SelectDateWidget

Reload the object edit page in your browser.  You should see all of
the Dublin Core fields we added, and the custom widgets for
description and date.  Go ahead and fill in some more fields and save
your changes.

While we're adding fields, let's change our display template so that
we can see any Dublin Core fields that are present, not just those
first three we started with.  Replace the title, creator, and date
lines in your ``repo/display.html`` template with this:

.. code-block:: django

    {% for el in dc.elements %}
        <tr><th>{{ el.name }}:</th><td>{{el}}</td</tr>
    {% endfor %}

Now when you load the object page in your browser, you should see all
of the fields that you entered data for on the edit page.

Search Fedora content
^^^^^^^^^^^^^^^^^^^^^

So far, we've just been working with the objects we uploaded, where we
know the PID of the object we want to view or edit.  But how do we
come back and find that again later?  Or find other content that
someone else created?  Let's build a simple search to find objects in
Fedora.

.. Note::

  For this tutorial, we'll us the Fedora **findObjects** API method.
  This search is quite limited, and for a production system, you'll
  probably want to use something more powerful, such as GSearch or
  Solr, but findObjects is enough to get you started.

.. TODO: link gsearch

The built-in fedora search can either do a keyword search across all
indexed fields *or* a fielded search.  For the purposes of this
tutorial, a simple keyword search will accomplish what we need.  Let's
create a simple form with one input for keyword search terms.  Add the
following to ``repo/forms.py``::

    class SearchForm(forms.Form):
        keyword = forms.CharField()

Add a search url to ``repo/urls.py``::

    url(r'^search/$', 'search', name='search'),

Then import the new form into ``repo/views.py`` and define the view
that will actually do the searching::

    from simplerepo.repo.forms import SearchForm

    def search(request):
        objects = None
        if request.method == 'POST':
            form = SearchForm(request.POST)
            if form.is_valid():
                repo = Repository()
                objects = list(repo.find_objects(form.cleaned_data['keyword'], type=FileObject))

        elif request.method == 'GET':
            form = SearchForm()
        return render_to_response('repo/search.html', {'form': form, 'objects': objects},
                context_instance=RequestContext(request))

As before, on a GET request we simple pass the form to the template for
display.  When the request is a POST with valid search data, we're going to
instantiate our :class:`~eulfedora.server.Repository` object and call the
:meth:`~eulfedora.server.Repository.find_objects` method. Since we're just
doing a term search, we can just pass in the keywords from the form.  If you
wanted to do a fielded search, you could build a keyword-argument style list
of fields and search terms instead. We're telling
:meth:`~eulfedora.server.Repository.find_objects` to return everything it
finds as an instance of our ``FileObject`` class for now, even though that
is an over-simplification and in searching across all content in the Fedora
repository we may well find other kinds of content.

Let's create a search template to display the search form and search
results.  Create ``repo/search.html`` in your templates directory and
add this:

.. code-block:: django

    <h1>Search for objects</h1>
    <form method="post">{% csrf_token %}
        {{ form.as_p }}
        <input type="submit" value="Submit"/>
    </form>
    {% if objects %}
        <hr/>
        {% for obj in objects %}
            <p><a href="{% url display obj.pid %}">{{ obj.label }}</a></p>
        {% endfor %}
    {% endif %}

This template will always display the search form, and if any objects were
found, it will list them.  Let's take it for a whirl!  Go to
`<http://localhost:8000/search/>`_ and enter a search term.  Try searching
for the object labels, any of the values you entered into the Dublin Core
fields that you edited, or if you're using ``simplerepo`` for your
configured ``PIDSPACE``, search on ``simplerepo:*`` to find the objects
you've uploaded.

When you are searching across disparate content in the Fedora repository,
depending on how you have access configured for that repository, there is a
possibility that the search could return an object that the current user
doesn't actually have permission to view. For efficiency reasons, the
:class:`~eulfedora.models.DigitalObject` postpones any Fedora API calls
until the last possibly moment-- which means that in our search results, any
connection errors will happen in the template instead of in the view method.
Fortunately, :mod:`eulfedora.templatetags` has a template tag to help with
that!  Let's rewrite the search template to use it:

.. code-block:: django

    {% load fedora %}
    <h1>Search for objects</h1>
    <form method="post">{% csrf_token %}
        {{ form.as_p }}
        <input type="submit" value="Submit"/>
    </form>
    {% if objects %}
        <hr/>
        {% for obj in objects %}
          {% fedora_access %}
            <p><a href="{% url display obj.pid %}">{{ obj.label }}</a></p>
          {% permission_denied %}
            <p>You don't have permission to view this object.</p>
          {% fedora_failed %}
            <p>There was an error accessing fedora.</p>
          {% end_fedora_access %}
        {% endfor %}
    {% endif %}

What we're doing here is loading the ``fedora`` template tag library, and
then using `fedora_access <../fedora.html#fedora-access>`_ for each object that
we want to display.  That way we can catch any permission or connection
errors and display some kind of message to the user, and still display all
the content they have permission to view.

For this template tag to work correctly, you're also going to have
disable template debugging (otherwise, the Django template debugging
will catch the error first).  Edit your ``settings.py`` and change
``TEMPLATE_DEBUG`` to False.
