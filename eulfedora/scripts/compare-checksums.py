#!/usr/bin/env python

import argparse
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

    parser = argparse.ArgumentParser()
    parser.add_argument('pids', metavar='PID', nargs='*')
    parser.add_argument('--fedora-root', dest='fedora_root', required=True)
    parser.add_argument('--fedora-user', dest='fedora_user', default=None)
#    parser.add_argument('--fedora-password', dest='fedora_password',
 #                       action=PasswordAction, default=None)

    parser.add_argument('--fedora-password', dest='fedora_password',
                        default=None)
    

    args = parser.parse_args()

    stats = defaultdict(int)

    repo = Repository(args.fedora_root, args.fedora_user, args.fedora_password)

    if args.pids:
        objects = (repo.get_object(pid) for pid in args.pids)
    else:
        objects = repo.find_objects()
    
    for obj in objects:
        for dsid in obj.ds_list.iterkeys():
            stats['ds'] += 1
            dsobj = obj.getDatastreamObject(dsid)
            if not dsobj.validate_checksum():
                print "%s/%s has an invalid checksum" % (obj.pid, dsid)
                stats['invalid_ds'] += 1

            # TODO: check if checksum type is DISABLED / checksum value none
        stats['objects'] += 1

    print "\nTested %(ds)d datastream(s) on %(objects)d object(s); found %(invalid_ds)d invalid checksum(s)" % \
          stats


class PasswordAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, getpass())

    


if __name__ == '__main__':
    main()
