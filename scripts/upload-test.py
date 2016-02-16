#!/usr/bin/env python

# Script for testing upload a file to Fedora to get an upload id for use as
# a datastream location.
# Example of using a callback method on the upload api call.
# Requires progressbar

import argparse
import base64
import os
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from progressbar import ProgressBar, Percentage, Bar, RotatingMarker, ETA, \
    FileTransferSpeed, AnimatedMarker
import pycurl

from eulfedora.server import Repository
from test import testsettings


def upload_file(filename):
    repo = Repository(testsettings.FEDORA_ROOT_NONSSL, testsettings.FEDORA_USER,
                      testsettings.FEDORA_PASSWORD)

    filesize = os.path.getsize(filename)
    widgets = ['Upload: ', Percentage(), ' ', Bar(),
               ' ', ETA(), ' ', FileTransferSpeed()]
    # set initial progressbar size based on file; will be slightly larger because
    # of multipart boundary content
    pbar = ProgressBar(widgets=widgets, maxval=filesize).start()

    def upload_callback(monitor):
        # update the progressbar to actual maxval (content + boundary)
        pbar.maxval = monitor.len
        # update current status
        pbar.update(monitor.bytes_read)

    with open(filename, 'rb') as f:
        upload_id = repo.api.upload(f, callback=upload_callback)
        pbar.finish()
        print upload_id


def curl_upload_file(filename):
    print 'curl upload'
    conn = pycurl.Curl()
    headers = {'Authorization' : 'Basic %s' % base64.b64encode("%s:%s" % (testsettings.FEDORA_USER, testsettings.FEDORA_PASSWORD))}
    conn.setopt(conn.URL, '%supload' % testsettings.FEDORA_ROOT_NONSSL)
    conn.setopt(pycurl.VERBOSE, 1)
    conn.setopt(pycurl.HTTPHEADER, ["%s: %s" % t for t in headers.items()])

    filesize = os.path.getsize(filename)
    widgets = ['Upload: ', Percentage(), ' ', Bar(),
               ' ', ETA(), ' ', FileTransferSpeed()]
    # set initial progressbar size based on file; will be slightly larger because
    # of multipart boundary content
    pbar = ProgressBar(widgets=widgets, maxval=filesize).start()

    def progress(dl_total, dl, up_total, up):
        # update the progressbar to actual maxval (content + boundary)
        pbar.maxval = up_total
        # update current status
        pbar.update(up)

    conn.setopt(conn.HTTPPOST, [
        ('file', (
            # upload the contents of this file
            conn.FORM_FILE, filename,
            # specify a different file name for the upload
            conn.FORM_FILENAME, 'file',
            # specify a different content type
            # conn.FORM_CONTENTTYPE, 'application/x-python',
        )),
    ])
    # conn.setopt(conn.CURLOPT_READFUNCTION)
    conn.setopt(conn.XFERINFOFUNCTION, progress)
    conn.setopt(conn.NOPROGRESS, False)

    conn.perform()

    # HTTP response code, e.g. 200.
    print 'Status: %d' % conn.getinfo(conn.RESPONSE_CODE)
    # Elapsed time for the transfer.
    print 'Time: %f' % conn.getinfo(conn.TOTAL_TIME)

    conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a file to fedora for use as datastream content')
    parser.add_argument('filename', metavar='FILE',
                        help='name of the file to upload')
    parser.add_argument('--curl', action='store_true',
                        help='upload with pycurl')

    args = parser.parse_args()
    if args.curl:
        curl_upload_file(args.filename)
    else:
        upload_file(args.filename)