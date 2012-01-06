#!/usr/bin/env python

# file eulfedora/scripts/compare-checksums.py
# 
#   Copyright 2012 Emory University Libraries
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

import argparse
import csv
from collections import defaultdict
from eulfedora.server import Repository
from getpass import getpass
import logging
from logging import config
import signal

logger = logging.getLogger(__name__)


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'basic': {
            'format': '[%(asctime)s] %(levelname)s:%(name)s::%(message)s',
            'datefmt': '%d/%b/%Y %H:%M:%S',
         },
    },
    'handlers': {
        'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter': 'basic'
        },
    },
    'loggers': {
        'root': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        # 'eulfedora': {
        #     'handlers': ['console'],
        #     'level': 'DEBUG',
        #     'propagate': True,
        # },
        # 'eulxml': {
        #     'handlers': ['console'],
        #     'level': 'DEBUG',
        #     'propagate': True,
        # },
    }
}

config.dictConfig(LOGGING)


class ValidateChecksums(object):

    stats = defaultdict(int)

    csv_file = None
    csv = None

    #used to break the look when a signal is caught
    interupted = False

    def run(self):
        # bind a handler for interrupt signal
        signal.signal(signal.SIGINT, self.interrupt_handler)

        parser = argparse.ArgumentParser(description='''Validate datastream checksums
        for Fedora repository content.  By default, iterates through all objects that
        are findable by the findObjects REST API and checks all datastreams.
        ''')
        parser.add_argument('pids', metavar='PID', nargs='*',
                            help='list specific pids to be checked (optional)')
        # fedora connection args
        repo_args = parser.add_argument_group('Fedora repository connection options')
        repo_args.add_argument('--fedora-root', dest='fedora_root', required=True,
                            help='URL for accessing fedora, e.g. http://localhost:8080/fedora/')
        repo_args.add_argument('--fedora-user', dest='fedora_user', default=None, 
                            help='Fedora username (requires permission to run compareDatastreamChecksum)')
        repo_args.add_argument('--fedora-password', dest='fedora_password', metavar='PASSWORD',
                            default=None, action=PasswordAction,
                            help='Password for the specified Fedora user (leave blank to be prompted)')

        # script options
        parser.add_argument('--csv-file', dest='csv_file', default=None,
                            help='Output results to the specified CSV file')
        parser.add_argument('--all-versions', '-a', dest='all_versions', action='store_true',
                        help='''Check all versions of datastreams
                        (by default, only current versions are checked)''')
        parser.add_argument('--quiet', '-q', dest='quiet', default=None, action='store_true',
                        help='Only outputs summary report')
        self.args = parser.parse_args()

        # if csv-file is specified, create the file and write the header row
        if self.args.csv_file:
            # TODO: error handling for file open/write failure
            self.csv_file = open(self.args.csv_file, 'wb')
            self.csv = csv.writer(self.csv_file,  quoting=csv.QUOTE_ALL)
            self.csv.writerow(['pid', 'datastream id', 'date created', 'status',
                               'mimetype', 'versioned'])

        repo = Repository(self.args.fedora_root, self.args.fedora_user, self.args.fedora_password)

        if self.args.pids:
            # if pids were specified on the command line, use those
            objects = (repo.get_object(pid) for pid in self.args.pids)
        else:
            # otherwise, process all find-able objects
            objects = repo.find_objects()
    
        for obj in objects:
            for dsid in obj.ds_list.iterkeys():
                dsobj = obj.getDatastreamObject(dsid)
                self.stats['ds'] += 1

                if self.args.all_versions:
                    # check every version of this datastream
                    history = obj.api.getDatastreamHistory(obj.pid, dsid)
                    for ds in history.datastreams:
                        self.check_datastream(dsobj, ds.createDate)
                        self.stats['ds_versions'] += 1

                else:
                    # current version only
                    self.check_datastream(dsobj)
                

            self.stats['objects'] += 1
            if self.interupted:
                break


        # summarize what was done
        totals = '\nTested %(objects)d object(s), %(ds)d datastream(s)' % self.stats
        if self.args.all_versions:
            totals += ', %(ds_versions)d datastream version(s)' % self.stats
        print totals
        print 'Found %(invalid)d invalid checksum(s)' % self.stats
        print 'Found %(missing)d datastream(s) with no checksum' % self.stats

        # if a csv file was opened, close it
        if self.csv_file:
            self.csv_file.close()


    def check_datastream(self, dsobj, date=None):
        '''Check the validity of a particular datastream.  Checks for
        invalid datastreams using
        :meth:`~eulfedora.models.DatastreamObject.validate_checksum`,
        and for no checksum (checksum type of ``DISABLED`` and
        checksum value of ``none``).  Optionally reports on the status
        and/or adds it to CSV file, depending on the arguments the
        script was called with.
        
        :param dsobj: :class:`~eulfedora.models.DatastreamObject` to
        be checked :param date: optional date/time for a particular
        version of the datastream to be checked; when not specified,
        the current version will be checked
        '''
        if not dsobj.validate_checksum(date=date):
            status = 'invalid'

        # if the checksum in fedora is stored as DISABLED/none,
        # validate_checksum will return True - but that may not be
        # what we want, so report as missing.
        elif dsobj.checksum_type == 'DISABLED' or dsobj.checksum == 'none':
            status = 'missing'
            
        else:
            status = 'ok'
            
        self.stats[status] += 1

        if status is not 'ok':
            if not self.args.quiet:
                print "%s/%s - %s checksum (%s)" % \
                      (dsobj.obj.pid, dsobj.id, status, date or dsobj.created)

            if self.csv:
                self.csv.writerow([dsobj.obj.pid, dsobj.id, dsobj.created, status,
                                   dsobj.mimetype, dsobj.versionable])

    def interrupt_handler(self, signum, frame):
        '''Gracefully handle a SIGINT, if possible. Sets a flag so main script
        loop can exit cleanly, and restores the default SIGINT behavior,
        so that a second interrupt will stop the script.
        '''
        if signum == signal.SIGINT:
            # restore default signal handler so a second SIGINT can be used to quit
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            # set interrupt flag so main loop knows to quit at a reasonable time
            self.interupted = True
            # report if script is in the middle of an object
            print "Finishing the current object, hit <CTRL> + C again to quit immediately"


class PasswordAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        # if a value was specified on the command-line, use that
        if value:
            setattr(namespace, self.dest, value)
        # otherwise, use getpass to prompt for a password
        else:
            setattr(namespace, self.dest, getpass())


if __name__ == '__main__':
    ValidateChecksums().run()
