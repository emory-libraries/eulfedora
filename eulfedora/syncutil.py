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
        size_estimate = estimate_object_size(src_obj)
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


    def __init__(self, obj, dest_repo, progress_bar=None):
        self.obj = obj
        self.dest_repo = dest_repo
        self.progress_bar = progress_bar
        self.processed_size = 0

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
        self.processed_size += len(self._current_chunk)
        return self._current_chunk

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
        # generator that can be used to upload to fedoro
        if self.progress_bar:
            self.progress_bar.start()

        while True:
            chunk = self.get_next_chunk()

            # check if this chunk includes start or end of binary content
            if self.has_binary_content(chunk):
                # split into chunks based on binary content tags
                # NOTE: could contain multiple small binary content
                # sections in a single chunk
                subsections = self.bincontent_regex.split(chunk)

                for section in self.process_chunk_sections(subsections):
                    yield section

                if self.partial_chunk:
                    sections = self.bincontent_regex.split(self.current_chunk())
                    for section in self.process_chunk_sections(sections[self.section_start_idx:]):
                        yield section


            # chunk without any binary content tags - yield normally
            else:
                yield chunk

            # store the end of the current chunk in case it is needed for
            # context when processing the next one
            if self.current_chunk():
                self.end_of_last_chunk = self.current_chunk()[-200:]
            else:
                self.end_of_last_chunk = chunk[-200:]

            # FIXME: in certain cases, some content is being yielded out of order

            # update progressbar if we have one
            self.update_progressbar()


    def process_chunk_sections(self, subsections):
        in_file = False
        for idx, content in enumerate(subsections):
            if content == '<foxml:binaryContent>':
                # get datastream info from the end of the section just before this one
                dsinfo = self.get_datastream_info(subsections[idx-1])
                # dsinfo = self.get_datastream_info(subsections[idx-1][-250:], idx-1)
                if dsinfo:
                    logger.info('Found encoded datastream %(id)s (%(mimetype)s, size %(size)s, %(type)s %(digest)s)',
                        dsinfo)
                # FIXME: error if datastream info is not found?

                in_file = True
                datagen = self.encoded_datastream(subsections[idx+1:])
                upload_id = self.dest_repo.api.upload(ReadableGenerator(datagen,
                    size=dsinfo['size']),
                    generator=True)
                    # streaming_iter=True, size=infomatch.groupdict()['size'])

                yield '<foxml:contentLocation REF="%s" TYPE="URL"/>' % upload_id

            elif content == '</foxml:binaryContent>':
                in_file = False

            elif in_file:
                # binary content within a file - ignore
                next

            else:
                # not start or end of binary content, and not
                # within a file, so yield as is (e.g., datastream tags
                # between small files)
                yield content

    # generator to iterate through sections and possibly next chunk
    # for upload to fedora
    def encoded_datastream(self, sections):
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
        found_end = False
        size = 0
        md5 = hashlib.md5()
        leftover = None
        while not found_end:
            for idx, content in enumerate(sections):
                if content == '</foxml:binaryContent>':
                    logger.info('Decoded content size %s (%s) MD5 %s',
                        size, humanize_file_size(size), md5.hexdigest())
                    found_end = True
                elif not found_end:
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

                    md5.update(decoded_content)
                    size += len(decoded_content)
                    yield decoded_content

                else:
                    # content is not a binaryContent tag and we are no longer
                    # within the encoded binary data, so this section
                    # and an following ones need to be processed by
                    # the object data generator

                    # set a flag to indicate partial content,
                    # with an index of where to start
                    self.partial_chunk = True
                    self.section_start_idx = idx
                    # stop processing
                    break

            # if binary data end was not found in the current chunk,
            # get the next chunk and keep processing
            if not found_end:
                chunk = self.get_next_chunk()
                self.update_progressbar()
                sections = self.bincontent_regex.split(chunk)

class ReadableGenerator(object):
    def __init__(self, gen, size):
        self.gen = gen
        self.size = size
        self.remainder = None
        self.total_read = 0

    def read(self, size=None):
        if size is None:
            # FIXME: doesn't this defeat the purpose of the generator?
            return ''.join(self.gen)
        print 'read size requested = ', size

        if self.remainder:
            data = self.remainder
            self.remainder = None
        else:
            data = ''

        while len(data) < size:
            data += self.gen.next()

        if len(data) > size:
            self.remainder = data[size:]

        self.total_read += len(data[:size])
        return data[:size]

        # next_chunk = self.gen.next()
        # # if chunk is bigger than requested
        # if len(next_chunk) > size:
        #     self.remainder = next_chunk[size:]
        #     return next_chunk[:size]

        # todo: handle size
        # while self.gen.next()
    def __len__(self):
        return int(self.size)


def estimate_object_size(obj):
    # calculate rough estimate of object size
    size_estimate = 250000   # initial rough estimate for foxml size
    for ds in obj.ds_list:
        dsobj = obj.getDatastreamObject(ds)
        for version in dsobj.history().versions:
            size_estimate += version.size

    # TODO: optionally support calculating base64 encoded size

    return size_estimate


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

