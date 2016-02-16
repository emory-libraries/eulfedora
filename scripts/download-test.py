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
import tempfile

from eulfedora.server import Repository
from test import testsettings



def download_file(pid, dsid):
    repo = Repository(testsettings.FEDORA_ROOT_NONSSL, testsettings.FEDORA_USER,
                      testsettings.FEDORA_PASSWORD)
    obj = repo.get_object(pid)
    ds = obj.getDatastreamObject(dsid)

    widgets = ['Download: ', Percentage(), ' ', Bar(),
               ' ', ETA(), ' ', FileTransferSpeed()]
    # set initial progressbar size based on file; will be slightly larger because
    # of multipart boundary content
    pbar = ProgressBar(widgets=widgets, maxval=ds.size).start()

    # download content to a tempfile
    tmpfile = tempfile.NamedTemporaryFile(
        prefix='%s-%s_' % (pid, dsid), delete=False)
    print 'writing to ', tmpfile.name
    size_read = 0
    try:
        for chunk in ds.get_chunked_content():
            size_read += len(chunk)
            pbar.update(size_read)
            tmpfile.write(chunk)
    except Exception:
        raise


def curl_download_file(pid, dsid):
    repo = Repository(testsettings.FEDORA_ROOT_NONSSL, testsettings.FEDORA_USER,
                      testsettings.FEDORA_PASSWORD)
    obj = repo.get_object(pid)
    ds = obj.getDatastreamObject(dsid)

    tmpfile = tempfile.NamedTemporaryFile(
        prefix='%s-%s_' % (pid, dsid), delete=False)
    print 'writing to ', tmpfile.name

    widgets = ['Upload: ', Percentage(), ' ', Bar(),
               ' ', ETA(), ' ', FileTransferSpeed()]
    # set initial progressbar size based on file; will be slightly larger because
    # of multipart boundary content
    pbar = ProgressBar(widgets=widgets, maxval=ds.size).start()

    def progress(dl_total, dl, up_total, up):
        # update current status
        pbar.update(dl)

    c = pycurl.Curl()
    headers = {'Authorization' : 'Basic %s' % \
        base64.b64encode("%s:%s" % (testsettings.FEDORA_USER, testsettings.FEDORA_PASSWORD))}
    c.setopt(pycurl.VERBOSE, 1)
    c.setopt(pycurl.HTTPHEADER, ["%s: %s" % t for t in headers.items()])

            # /objects/{pid}/datastreams/{dsID}/content ? [asOfDateTime] [download]
    c.setopt(c.URL, '%sobjects/%s/datastreams/%s/content' % \
        (testsettings.FEDORA_ROOT_NONSSL, pid, dsid))
    # c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.WRITEFUNCTION, tmpfile.write)
    c.setopt(c.XFERINFOFUNCTION, progress)
    c.setopt(c.NOPROGRESS, False)
    c.perform()

    # HTTP response code, e.g. 200.
    print 'Status: %d' % c.getinfo(c.RESPONSE_CODE)
    # Elapsed time for the transfer.
    print 'Time: %f' % c.getinfo(c.TOTAL_TIME)

    c.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a file to fedora for use as datastream content')
    parser.add_argument('pid', metavar='pid',
                        help='pid to download from')
    parser.add_argument('ds', metavar='dsid',
                        help='id of datastream to download')
    parser.add_argument('--curl', action='store_true',
                        help='upload with pycurl')

    args = parser.parse_args()
    if args.curl:
        curl_download_file(args.pid, args.ds)
    else:
        download_file(args.pid, args.ds)