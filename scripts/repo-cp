#!/usr/bin/env python

# file scripts/repo-cp
#
#   Copyright 2015 Emory University Libraries & IT Services
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
import ConfigParser
import math
import os

from eulxml.xmlmap import load_xmlobject_from_string
from eulfedora.server import Repository
from eulfedora.util import ChecksumMismatch, PermissionDenied, \
    RequestFailed
from eulfedora.xml import FoxmlDigitalObject

try:
    from progressbar import ProgressBar, Bar, Counter, ETA, \
        FileTransferSpeed, Percentage, \
        RotatingMarker, SimpleProgress, Timer
except ImportError:
    ProgressBar = None



def repo_copy():

    parser = argparse.ArgumentParser()

    # config file options
    cfg_args = parser.add_argument_group('Config file options')
    cfg_args.add_argument('--config', '-c',
        default='$HOME/.repocpcfg',
        help='Load the specified config file (default: %(default)s')

    cfg_args.add_argument('source',
        help='Source repository for content to be copied')
    cfg_args.add_argument('dest',
        help='Destination repository for content to be copied')

    # list of pids
    parser.add_argument('pids', metavar='PID', nargs='*',
                                 help='list of pids to copy')

    args = parser.parse_args()

    cfg = ConfigParser.ConfigParser()
    configfile_path = args.config.replace('$HOME', os.environ['HOME'])
    with open(configfile_path) as cfgfile:
            cfg.readfp(cfgfile)

    if not cfg.has_section(args.source):
        print 'Source repository %s is not configured' % args.source
        return
    if not cfg.has_section(args.dest):
        print 'Destination repository %s is not configured' % args.dest
        return

    src_repo = Repository(cfg.get(args.source, 'fedora_root'),
        cfg.get(args.source, 'fedora_user'),
        cfg.get(args.source, 'fedora_password'))

    dest_repo = Repository(cfg.get(args.dest, 'fedora_root'),
        cfg.get(args.dest, 'fedora_user'),
        cfg.get(args.dest, 'fedora_password'))

    if ProgressBar:
        widgets = [FileSizeCounter(), ' ', FileTransferSpeed(), ' ',
                   Timer(format='%s')] # time only, no label like "elapsed time: 00:00"
        pbar = ProgressBar(widgets=widgets, maxval=1024*1024*1024*1024).start()
    else:
        pbar = None


    for pid in args.pids:
        try:
            src_obj = src_repo.get_object(pid)
            # calculate rough estimate of object size
            size_estimate = 250000   # start rough estimate for foxml size
            for ds in src_obj.ds_list:
                dsobj = src_obj.getDatastreamObject(ds)
                for version in dsobj.history().versions:
                    size_estimate += version.size
            if pbar:
                pbar.maxval = size_estimate

            print 'size estimate is %d (%s)' % (size_estimate, humanize_file_size(size_estimate))

            # response = src_repo.api.export(pid, context='migrate')
            response = src_repo.api.export(pid, context='archive', stream=True)

            # generator to read src repo request in chunks and stream
            # to dest repo
            def export_data():
                size = 0
                for chunk in response.iter_content(4096*1024):
                    size += len(chunk)
                    # update progressbar if we have one
                    if pbar:
                        # progressbar doesn't like it when size exceeds maxval,
                        # but we don't actually know maxval; adjust the maxval up
                        # when necessary
                        if pbar.maxval < size:
                            pbar.maxval = size
                        pbar.update(size)
                    yield chunk

        except RequestFailed as err:
            err_type = 'Error'
            if isinstance(err, PermissionDenied):
                err_type = 'Permission denied'
            err_msg = unicode(err)
            if '404' in err_msg:
                err_msg = 'object not found'
            print '%s exporting %s from %s: %s' % \
                (err_type, pid, args.source, err_msg)

            continue

        dest_obj = dest_repo.get_object(pid)
        if dest_obj.exists:
            if cfg.has_option(args.dest, 'allow_overwrite') and \
              cfg.getboolean(args.dest, 'allow_overwrite'):

                print '%s already exists in %s, purging' % (pid, args.dest)
                try:
                    dest_repo.purge_object(pid)
                except RequestFailed as err:
                    err_type = 'Error'
                    if isinstance(err, PermissionDenied):
                        err_type = 'Permission denied'
                    print '%s purging %s from %s: %s' % \
                        (err_type, pid, args.dest, err)
                    # if object exists and purge fails, go to next pid
                    continue
            else:
                print '%s already exists in %s but overwrite is not allowed; skipping'\
                    % (pid, args.dest)
                continue

        try:
            if pbar:
                pbar.start()
            result = dest_repo.ingest(export_data())
            if pbar:
                pbar.finish()
            print '%s copied' % result
        except ChecksumMismatch:
            # print 'ChecksumMismatch on %s, removing checksums for DC/RELS-EXT' % pid
            print 'ChecksumMismatch on %s' % pid
            # export_xml = load_xmlobject_from_string(export, FoxmlDigitalObject)
            # for ds in export_xml.datastreams:
            #     print ds.id
            #     if ds.id in ['DC', 'RELS-EXT']:
            #         for version in ds.versions:
            #             del version.content_digest

            # result = dest_repo.ingest(export_xml.serialize(pretty=True))
            # print '%s copied' % result


        except RequestFailed as err:
            err_type = 'Error'
            if isinstance(err, PermissionDenied):
                err_type = 'Permission denied'
            print '%s importing %s to %s: %s' % \
                (err_type, pid, args.dest, err)

            continue



def humanize_file_size(size):
    # human-readable file size from
    # http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    size = abs(size)
    if size == 0:
        return "0B"
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    p = math.floor(math.log(size, 2)/10)
    return "%.2f%s" % (size/math.pow(1024, p), units[int(p)])


class FileSizeCounter(Counter):
    # file size counter widget for progressbar

    def update(self, pbar):
        return humanize_file_size(pbar.currval)



if __name__ == '__main__':
    repo_copy()