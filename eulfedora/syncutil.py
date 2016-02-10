# file eulfedora/syncutil.py
#
#   Copyright 2016 Emory University Libraries & IT Services
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


import binascii
import cStringIO
import hashlib
import logging
import math
import re

try:
    from progressbar import ProgressBar, Bar, Counter, ETA, \
        FileTransferSpeed, Percentage, \
        RotatingMarker, SimpleProgress, Timer
except ImportError:
    ProgressBar = None


logger = logging.getLogger(__name__)


def sync_object(src_obj, dest_repo, overwrite=False, show_progress=False):
    # calculate rough estimate of object size

    if show_progress and ProgressBar:
        print 'normal size estimate = ', estimate_object_size(src_obj)
        print 'base64 size_estimate = ', estimate_object_size(src_obj, archive=True)
        size_estimate = estimate_object_size(src_obj, archive=True)
        # create a new progress bar with current pid and size
        widgets = [src_obj.pid,
            ' Estimated size: %s || ' % humanize_file_size(size_estimate),
            'Transferred: ', FileSizeCounter(), ' ', FileTransferSpeed(), ' ',
             Timer(format='%s') # time only, no label like "elapsed time: 00:00"
            ]
        pbar = ProgressBar(widgets=widgets, maxval=size_estimate)
    else:
        pbar = None

    # TODO: support migrate/archive option
    export = ArchiveExport(src_obj, dest_repo,
        progress_bar=pbar)

    dest_obj = dest_repo.get_object(src_obj.pid)
    if dest_obj.exists:
        if overwrite:
            dest_repo.purge_object(src_obj.pid)
        else:
            # exception maybe?
            return  # error

    result = dest_repo.ingest(export.object_data())
    # log ?
    print '%s copied' % result
    if pbar:
        pbar.finish()


class ArchiveExport(object):

    # regex to match start or end of binary content
    bincontent_regex = re.compile(r'(</?foxml:binaryContent>)')
    # regex to pull out datastream version information
    dsinfo_regex = re.compile(r'ID="(?P<id>[^"]+)".*MIMETYPE="(?P<mimetype>[^"]+)".*SIZE="(?P<size>\d+)".* TYPE="(?P<type>[^"]+)".*DIGEST="(?P<digest>[0-9a-f]+)"',
        flags=re.MULTILINE|re.DOTALL)


    def __init__(self, obj, dest_repo, verify=False, progress_bar=None):
        self.obj = obj
        self.dest_repo = dest_repo
        self.verify = verify
        self.progress_bar = progress_bar
        self.processed_size = 0
        self.foxml_buffer = cStringIO.StringIO()
        self.within_file = False

    _export_response = None
    def get_export(self):
        if self._export_response is None:
            self._export_response = self.obj.api.export(self.obj.pid,
                context='archive', stream=True)
        return self._export_response

    read_block_size = 4096*1024*1024

    _iter_content = None
    def export_iterator(self):
        if self._iter_content is None:
            # self._iter_content = self.get_export().iter_content(2048)  # testing, to exaggerate problems
            self._iter_content = self.get_export().iter_content(self.read_block_size)
        return self._iter_content

    _current_chunk = None
    def current_chunk(self):
        return self._current_chunk

    partial_chunk = False
    section_start_idx = None
    end_of_last_chunk = None

    def get_next_chunk(self):
        self.partial_chunk = False
        if self._iter_content is None:
            self.export_iterator()

        if self._current_chunk is not None:
            self.end_of_last_chunk = self._current_chunk[-200:]

        self._current_chunk = self._iter_content.next()
        return self._current_chunk

    _current_sections = None
    def get_next_section(self):
        if self._current_sections is None:
            if self._current_chunk is None:
                self.get_next_chunk()
            self._current_sections = self.bincontent_regex.split(self.current_chunk())

        if self._current_sections:
            next_section = self._current_sections.pop(0)
            self.processed_size += len(next_section)
            self.update_progressbar()
            return next_section
        else:
            # if current list of sections is empty, look for more content
            # this will raise stop iteration at end of content
            self.get_next_chunk()
            self._current_sections = self.bincontent_regex.split(self.current_chunk())
            return self.get_next_section()

    def has_binary_content(self, chunk):
        ''''Use a regular expression to check if the current chunk
        includes the start or end of binary content.'''
        return self.bincontent_regex.search(chunk)

    def get_datastream_info(self, dsinfo):
        '''Use regular expressions to pull datastream [version]
        details (id, mimetype, size, and checksum) for binary content,
        in order to sanity check the decoded data.

        :param dsinfo: text content just before a binaryContent tag
        :returns: dict with keys for id, mimetype, size, type and digest,
            or None if no match is found
        '''
        # we only need to look at the end of this section of content
        dsinfo = dsinfo[-250:]
        # if not enough content is present, include the end of
        # the last read chunk, if available
        if len(dsinfo) < 250 and self.end_of_last_chunk is not None:
            dsinfo = self.end_of_last_chunk + dsinfo

        infomatch = self.dsinfo_regex.search(dsinfo)
        if infomatch:
            return infomatch.groupdict()


    def update_progressbar(self):
        # update progressbar if we have one
        if self.progress_bar is not None:
            # progressbar doesn't like it when size exceeds maxval,
            # but we don't actually know maxval; adjust the maxval up
            # when necessary
            if self.progress_bar.maxval < self.processed_size:
                self.progress_bar.maxval = self.processed_size
            self.progress_bar.update(self.processed_size)


    def object_data(self):
        # todo: docstring
        self.foxml_buffer = cStringIO.StringIO()

        if self.progress_bar:
            self.progress_bar.start()

        previous_section = None
        while True:
            try:
                section = self.get_next_section()
            except StopIteration:
                break

            if section == '<foxml:binaryContent>':
                self.within_file = True

                # get datastream info from the end of the section just before this one
                # (needed to provide size to upload request)
                dsinfo = self.get_datastream_info(previous_section)
                # dsinfo = self.get_datastream_info(subsections[idx-1][-250:], idx-1)
                if dsinfo:
                    logger.info('Found encoded datastream %(id)s (%(mimetype)s, size %(size)s, %(type)s %(digest)s)',
                        dsinfo)
                # FIXME: error if datastream info is not found?


                upload_id = self.dest_repo.api.upload(self.encoded_datastream(),
                    size=int(dsinfo['size']))

                self.foxml_buffer.write('<foxml:contentLocation REF="%s" TYPE="URL"/>' \
                    % upload_id)

            elif section == '</foxml:binaryContent>':
                # should not occur here; this section will be processed by
                # encoded_datastream method
                self.within_file = False

            elif self.within_file:
                # should not occur here; this section will be pulled by
                # encoded_datastream method

                # binary content within a file - ignore here
                # (handled by encoded_datastream method)
                next

            else:
                # not start or end of binary content, and not
                # within a file, so yield as is (e.g., datastream tags
                # between small files)
                self.foxml_buffer.write(section)

            previous_section = section

        return self.foxml_buffer


    # generator to iterate through sections and possibly next chunk
    # for upload to fedora
    def encoded_datastream(self):
        '''Generator for datastream content. Takes a list of sections
        of data within the current chunk (split on binaryContent start and
        end tags), runs a base64 decode, and yields the data.  Computes
        datastream size and MD5 as data is decoded for sanity-checking
        purposes.  If binary content is not completed within the current
        chunk, it will retrieve successive chunks of export data until it
        finds the end.  Sets a flag when partial content is left within
        the current chunk for continued processing by :meth:`object_data`.

        :param sections: list of export data split on binary content start
            and end tags, starting with the first section of binary content
        '''

        # return a generator of data to be uploaded to fedora
        size = 0
        if self.verify:
            md5 = hashlib.md5()
        leftover = None

        while self.within_file:
            content = self.get_next_section()
            if content == '</foxml:binaryContent>':
                if self.verify:
                    logger.info('Decoded content size %s (%s) MD5 %s',
                        size, humanize_file_size(size), md5.hexdigest())

                self.within_file = False

            elif self.within_file:
                content[:50]
                # if there was leftover binary content from the last chunk,
                # add it to the content now
                if leftover is not None:
                    content = ''.join([leftover, content])
                    leftover = None

                try:
                    # decode method used by base64.decode
                    decoded_content = binascii.a2b_base64(content)
                except binascii.Error:
                    # decoding can fail with a padding error when
                    # a line of encoded content runs across a read chunk
                    lines = content.split('\n')
                    # decode and yield all but the last line of encoded content
                    decoded_content = binascii.a2b_base64(''.join(lines[:-1]))
                    # store the leftover to be decoded with the next chunk
                    leftover = lines[-1]

                if self.verify:
                    md5.update(decoded_content)

                size += len(decoded_content)
                yield decoded_content


def estimate_object_size(obj, archive=True):
    # calculate rough estimate of object size
    size_estimate = 250000   # initial rough estimate for foxml size
    for ds in obj.ds_list:
        dsobj = obj.getDatastreamObject(ds)
        for version in dsobj.history().versions:
            if archive and version.control_group == 'M':
                size_estimate += base64_size(version.size)
            else:
                size_estimate += version.size

    return size_estimate

def base64_size(input_size):
    # from http://stackoverflow.com/questions/1533113/calculate-the-size-to-a-base-64-encoded-message
    adjustment = 3 - (input_size % 3) if (input_size % 3) else 0
    code_padded_size = ((input_size + adjustment) / 3) * 4
    newline_size = ((code_padded_size) / 76) * 1
    return code_padded_size + newline_size


def humanize_file_size(size):
    # human-readable file size from
    # http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    size = abs(size)
    if size == 0:
        return "0B"
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    p = math.floor(math.log(size, 2)/10)
    return "%.2f%s" % (size/math.pow(1024, p), units[int(p)])


if ProgressBar:
    class FileSizeCounter(Counter):
        # file size counter widget for progressbar

        def update(self, pbar):
            return humanize_file_size(pbar.currval)

