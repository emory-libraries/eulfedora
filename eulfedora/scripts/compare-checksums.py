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


def main():

    parser = argparse.ArgumentParser(description='''Validate datastream checksums
    for Fedora repository content.  By default, iterates through all objects that
    are findable by the findObjects REST API and checks all datastreams.
    ''')
    parser.add_argument('pids', metavar='PID', nargs='*',
                        help='list specific pids to be checked (optional)')
    parser.add_argument('--fedora-root', dest='fedora_root', required=True,
                        help='URL for accessing fedora, e.g. http://localhost:8080/fedora/')
    parser.add_argument('--fedora-user', dest='fedora_user', default=None, 
                        help='Fedora username (requires permission to run compareDatastreamChecksum)')
    # TODO: make both options available?
    # prompt for password, but allow passing on command-line in dev/staging
    # parser.add_argument('--fedora-password', dest='fedora_password',
    #                      action=PasswordAction, default=None)
    parser.add_argument('--fedora-password', dest='fedora_password', metavar='PASSWORD',
                        default=None, help='Password for the specified Fedora user')
    parser.add_argument('--csv-file', dest='csv_file', default=None,
                        help='Output results to the specified CSV file')
    parser.add_argument('--quiet', dest='quiet', default=None, action='store_true',
                        help='Only outputs summary report')

    args = parser.parse_args()

    stats = defaultdict(int)

    #if csv-file is specified create the file and write the header row
    if args.csv_file:
        csv_file = csv.writer(open(args.csv_file, 'wb'),  quoting=csv.QUOTE_ALL)
        csv_file.writerow(['PID', 'DSID', 'CREATED', "STATUS"])

    repo = Repository(args.fedora_root, args.fedora_user, args.fedora_password)

    if args.pids:
        # if pids were specified on the command line, use those
        objects = (repo.get_object(pid) for pid in args.pids)
    else:
        # otherwise, process all find-able objects
        objects = repo.find_objects()
    
    for obj in objects:
        for dsid in obj.ds_list.iterkeys():
            stats['ds'] += 1
            dsobj = obj.getDatastreamObject(dsid)
            if not dsobj.validate_checksum():
                if not args.quiet:
                    print "%s/%s has an invalid checksum (%s)" % (obj.pid, dsid, dsobj.created)
                stats['invalid'] += 1
                if args.csv_file:
                    csv_file.writerow([obj.pid, dsid, dsobj.created, "INVALID"])
            elif dsobj.checksum_type == 'DISABLED' or dsobj.checksum == 'none':
                if not args.quiet:
                    print "%s/%s has no checksum (%s)" % (obj.pid, dsid, dsobj.created)
                stats['missing'] += 1
                if args.csv_file:
                    csv_file.writerow([obj.pid, dsid, dsobj.created, "MISSING"])

        stats['objects'] += 1

    print '\nTested %(ds)d datastream(s) on %(objects)d object(s)' % stats
    print 'Found %(invalid)d invalid checksum(s)' % stats
    print 'Found %(missing)d datastream(s) with no checksum' % stats

    if args.csv_file:
        csv_file.writerow([]) # blank row
        csv_file.writerow(['Tested %(ds)d datastream(s) on %(objects)d object(s)' % stats])
        csv_file.writerow(['Found %(invalid)d invalid checksum(s)' % stats])
        csv_file.writerow(['Found %(missing)d datastream(s) with no checksum' % stats])



class PasswordAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, getpass())

    


if __name__ == '__main__':
    main()
