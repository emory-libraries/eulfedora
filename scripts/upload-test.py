#!/usr/bin/env python

# Script for testing upload a file to Fedora to get an upload id for use as
# a datastream location.
# Example of using a callback method on the upload api call.
# Requires progressbar

import argparse
import os
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from progressbar import ProgressBar, Percentage, Bar, RotatingMarker, ETA, \
    FileTransferSpeed, AnimatedMarker

from eulfedora.server import Repository
import testsettings


def upload_file(filename):
    global pbar
    repo = Repository(testsettings.FEDORA_ROOT_NONSSL, testsettings.FEDORA_USER,
                      testsettings.FEDORA_PASSWORD)

    filesize =  os.path.getsize(filename)
    widgets = ['Upload: ', Percentage(), ' ', Bar(),
               ' ', ETA(), ' ', FileTransferSpeed()]
    # set initial progressbar size based on file; will be slightly larger because
    # of multipart boundary content
    pbar = ProgressBar(widgets=widgets, maxval=filesize).start()

    def upload_callback(monitor):
        # update the progressbar to actual maxval (content + boundary)
        pbar.maxval = len(monitor)
        # update current status
        pbar.update(monitor.bytes_read)

    with open(filename, 'rb') as f:
        upload_id = repo.api.upload(f, callback=upload_callback)
        pbar.finish()
        print upload_id

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a file to fedora for use as datastream content')
    parser.add_argument('filename', metavar='FILE',
                        help='name of the file to upload')
    args = parser.parse_args()
    upload_file(args.filename)