# file eulfedora/management/commands/syncrepo.py
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

from getpass import getpass
import glob
import logging
import os
import sys
from optparse import make_option

from django.core.management.base import BaseCommand
try:
    # newer versions of django
    from django.apps import apps as django_apps
except ImportError:
    from django.db.models import get_apps
    apps = None


from eulfedora.server import Repository
from eulfedora.models import ContentModel, DigitalObject
from eulfedora.util import RequestFailed

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    def get_password_option(option, opt, value, parser):
        setattr(parser.values, option.dest, getpass())

    help = """Generate missing Fedora content model objects and load initial objects."""

    # NOTE: will need to be converted to add_argument / argparse
    # format for django 11 (optparse will be removed)
    option_list = BaseCommand.option_list + (
        make_option('--username', '-u',
                    dest='username',
                    action='store',
                    help='''Username to connect to fedora'''),
        make_option('--password',
                    dest='password',
                    action='callback', callback=get_password_option,
                    help='''Prompt for password required when username used'''
                ))

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def handle(self, *args, **options):

        repo_args = {}
        if options.get('username') is not None:
            repo_args['username'] = options.get('username')
        if options.get('password') is not None:
            repo_args['password'] = options.get('password')

        self.repo = Repository(**repo_args)


        self.verbosity = int(options.get('verbosity', 1))

        # FIXME/TODO: add count/summary info for content models objects created ?
        if self.verbosity > 1:
            sys.stdout.write("Generating content models for %d classes"
                             % len(DigitalObject.defined_types))

        for cls in DigitalObject.defined_types.itervalues():
            self.process_class(cls)

        self.load_initial_objects()

    def process_class(self, cls):
        try:
            ContentModel.for_class(cls, self.repo)
        except ValueError as v:
            # for_class raises a ValueError when a class has >1
            # CONTENT_MODELS.
            if self.verbosity > 1:
                sys.stderr.write(v)
        except RequestFailed as rf:
            if hasattr(rf, 'detail'):
                if 'ObjectExistsException' in rf.detail:
                    # This shouldn't happen, since ContentModel.for_class
                    # shouldn't attempt to ingest unless the object doesn't exist.
                    # In some cases, Fedora seems to report that an object doesn't exist,
                    # then complain on attempted ingest.

                    full_name = '%s.%s' % (cls.__module__, cls.__name__)
                    logger.warn('Fedora error (ObjectExistsException) on Content Model ingest for %s' % \
                                full_name)
                else:
                    # if there is a detail message, display that
                    sys.stderr.write("Error ingesting ContentModel for %s: %s"
                                     % (cls, rf.detail))

    def load_initial_objects(self):
        # look for any .xml files in apps under fixtures/initial_objects
        # and attempt to load them as Fedora objects
        # NOTE! any fixtures should have pids specified, or new versions of the
        # fixture will be created every time syncrepo runs

        app_module_paths = []

        if hasattr(django_apps, 'get_app_configs'):
            apps = django_apps.get_app_configs()
        else:
            apps = get_apps()

        # monkey see django code, monkey do
        for app in apps:
            # newer django AppConfig
            if hasattr(app, 'path'):
                app_module_paths.append(app.path)
            elif hasattr(app, '__path__'):
                # It's a 'models/' subpackage
                for path in app.__path__:
                    app_module_paths.append(path)
            else:
                # It's a models.py module
                app_module_paths.append(app.__file__)

        app_fixture_paths = [os.path.join(os.path.dirname(path),
                                          'fixtures', 'initial_objects', '*.xml')
                             for path in app_module_paths]
        fixture_count = 0
        load_count = 0

        for path in app_fixture_paths:
            fixtures = glob.iglob(path)
            for f in fixtures:
                # FIXME: is there a sane, sensible way to shorten file path for error/success messages?
                fixture_count += 1
                with open(f) as fixture_data:
                    # rather than pulling PID from fixture and checking if it already exists,
                    # just ingest and catch appropriate excetions
                    try:
                        pid = self.repo.ingest(fixture_data.read(), "loaded from fixture")
                        if self.verbosity > 1:
                            self.stdout.write("Loaded fixture %s as %s" % (f, pid))
                        load_count += 1
                    except RequestFailed as rf:
                        if hasattr(rf, 'detail'):
                            if 'ObjectExistsException' in rf.detail or \
                              'already exists in the registry; the object can\'t be re-created' in rf.detail:
                                if self.verbosity > 1:
                                    self.stdout.write("Fixture %s has already been loaded" % f)
                            elif 'ObjectValidityException' in rf.detail:
                                # could also look for: fedora.server.errors.ValidationException
                                # (e.g., RELS-EXT about does not match pid)
                                self.stdout.write("Error: fixture %s is not a valid Repository object" % f)
                            else:
                                # if there is at least a detail message, display that
                                self.stdout.write("Error ingesting %s: %s" %
                                                  (f, rf.detail))
                        else:
                            raise rf

        # summarize what was actually done
        if self.verbosity > 0:
            if fixture_count == 0:
                self.stdout.write("No fixtures found")
            else:
                self.stdout.write("Loaded %d object(s) from %d fixture(s)"
                                  % (load_count, fixture_count))
