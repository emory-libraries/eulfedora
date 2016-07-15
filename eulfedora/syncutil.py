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
import io
import logging
import math
import re
import six
from six.moves.urllib.parse import urlparse

try:
    import progressbar
except ImportError:
    progressbar = None

from eulfedora.util import force_bytes, force_text


logger = logging.getLogger(__name__)


def sync_object(src_obj, dest_repo, export_context='migrate',
                overwrite=False, show_progress=False,
                requires_auth=False, omit_checksums=False):
    '''Copy an object from one repository to another using the Fedora
    export functionality.

    :param src_obj: source :class:`~eulfedora.models.DigitalObject` to
        be copied
    :param dest_repo: destination  :class:`~eulfedora.server.Repository`
        where the object will be copied to
    :param export_context: Fedora export format to use, one of "migrate"
        or "archive"; migrate is generally faster, but requires access
        from destination repository to source and may result in checksum
        errors for some content; archive exports take longer to process
        (default: migrate)
    :param overwrite: if an object with the same pid is already present
        in the destination repository, it will be removed only if
        overwrite is set to true (default: false)
    :param show_progress: if True, displays a progress bar with content size,
        progress, speed, and ETA (only applicable to archive exports)
    :param requires_auth: content datastreams require authentication,
        and should have credentials patched in (currently only supported
        in archive-xml export mode)  (default: False)
    :param omit_checksums: scrubs contentDigest -- aka checksums -- from datastreams;
        helpful for datastreams with Redirect (R) or External (E) contexts
        (default: False)
    :returns: result of Fedora ingest on the destination repository on
        success
    '''

    # NOTE: currently exceptions are expected to be handled by the
    # calling method; see repo-cp script for an example

    if show_progress and progressbar:
        # calculate rough estimate of object size
        size_estimate = estimate_object_size(src_obj,
            archive=(export_context in ['archive', 'archive-xml']))
        # create a new progress bar with current pid and size
        widgets = [src_obj.pid,
            ' Estimated size: %s // ' % humanize_file_size(size_estimate),
            'Read: ', progressbar.widgets.DataSize(), ' ',
            progressbar.widgets.AdaptiveTransferSpeed(), ' ',
            '| Uploaded: ', progressbar.widgets.DataSize(value='upload'), ' // ',
            # FileTransferSpeed('upload'), currently no way to track upload speed...
             progressbar.widgets.Timer(), ' | ', progressbar.widgets.AdaptiveETA()
            ]

        class DownUpProgressBar(progressbar.ProgressBar):
            upload = 0
            def data(self):
                data = super(DownUpProgressBar, self).data()
                data['upload'] = self.upload
                return data

        pbar = DownUpProgressBar(widgets=widgets, max_value=size_estimate)
    else:
        pbar = None

    # migrate export can simply be read and uploaded to dest fedora
    if export_context == 'migrate':
        response = src_obj.api.export(src_obj, context=export_context, stream=True)
        export_data = response.iter_content(4096*1024)

    # archive export needs additional processing to handle large binary content
    elif export_context in ['archive', 'archive-xml']:
        export = ArchiveExport(src_obj, dest_repo,
            progress_bar=pbar, requires_auth=requires_auth,
            xml_only=(export_context == 'archive-xml'))
        # NOTE: should be possible to pass BytesIO to be read, but that is failing
        export_data = export.object_data().getvalue()       

    else:
        raise Exception('Unsupported export context %s', export_context)

    # wipe checksums from FOXML if flagged in options
    if omit_checksums:
        export_data = re.sub(r'<foxml:contentDigest.+?/>', '', export_data)

    dest_obj = dest_repo.get_object(src_obj.pid)
    if dest_obj.exists:
        if overwrite:
            dest_repo.purge_object(src_obj.pid)
        else:
            # exception ?
            return False

    result = dest_repo.ingest(export_data)
    if pbar:
        pbar.finish()
    return force_text(result)

## constants for binary content end and start
#: foxml binary content start tag
BINARY_CONTENT_START = b'<foxml:binaryContent>'
#: foxml binary content end tag
BINARY_CONTENT_END = b'</foxml:binaryContent>'


class ArchiveExport(object):
    '''Iteratively process a Fedora archival export in order to copy
    an object into another fedora repository.  Use :meth:`object_data`
    to process the content and provides the foxml to be ingested into
    the destination repository.

    :param obj: source :class:`~eulfedora.models.DigitalObject` to
        be copied
    :param dest_repo: destination :class:`~eulfedora.server.Repository`
        where the object will be copied to
    :param verify: if True, datastream sizes and MD5 checksums will
        be calculated as they are decoded and logged for verification
        (default: False)
    :param progress_bar: optional progressbar object to be updated as
        the export is read and processed
    :param requires_auth: content datastreams require authentication,
        and should have credentials patched in; currently only relevant
        when xml_only is True. (default: False)
    :param xml_only: only use archival data for xml datastreams;
        use fedora datastream dissemination urls for all non-xml content
        (optionally with credentials, if requires_auth is set).
        (default: False)
    '''



    #: regular expression used to identify datastream version information
    #: that is needed for processing datastream content in an archival export
    dsinfo_regex = re.compile(r'ID="(?P<id>[^"]+)".*CREATED="(?P<created>[^"]+)".*MIMETYPE="(?P<mimetype>[^"]+)".*SIZE="(?P<size>\d+)".*TYPE="(?P<type>[^"]+)".*DIGEST="(?P<digest>[0-9a-f]*)"',
        flags=re.MULTILINE|re.DOTALL)
    # NOTE: regex allows for digest to be empty

    #: url credentials, if needed for datastream content urls
    url_credentials = ''

    def __init__(self, obj, dest_repo, verify=False, progress_bar=None,
        requires_auth=False, xml_only=False):
        self.obj = obj
        self.dest_repo = dest_repo
        self.verify = verify
        self.xml_only = xml_only
        self.progress_bar = progress_bar
        if requires_auth:
            # if auth is required, create a credentials string
            # in format to be inserted into a url
            self.url_credentials = '%s:%s@' % (obj.api.username, obj.api.password)

        self.processed_size = 0
        self.foxml_buffer = io.BytesIO()
        self.within_file = False

    _export_response = None
    def get_export(self):
        if self._export_response is None:
            self._export_response = self.obj.api.export(self.obj.pid,
                context='archive', stream=True)
        return self._export_response

    read_block_size = 4096*1024*1024

    _iter_content = None

    _current_chunk = None
    def current_chunk(self):
        return self._current_chunk

    partial_chunk = False
    section_start_idx = None
    end_of_last_chunk = None
    _chunk_leftover = b''

    def get_next_chunk(self):
        self.partial_chunk = False
        if self._iter_content is None:
            self._iter_content = self.get_export().iter_content(self.read_block_size)

        if self._current_chunk is not None:
            self.end_of_last_chunk = self._current_chunk[-400:]

        self._current_chunk = self._chunk_leftover + six.next(self._iter_content)

        # check if chunk ends with a partial binary content tag
        len_to_save = (endswith_partial(self._current_chunk, BINARY_CONTENT_START) \
                    or endswith_partial(self._current_chunk, BINARY_CONTENT_END))
        # if it does, save that content for the next chunk
        if len_to_save:
            self._chunk_leftover = self._current_chunk[-len_to_save:]
            self._current_chunk = self._current_chunk[:-len_to_save]
        else:
            self._chunk_leftover = b''

        return self._current_chunk

    _current_sections = None
    def get_next_section(self):
        if self._current_sections is None:
            if self._current_chunk is None:
                self.get_next_chunk()

            self._current_sections = list(binarycontent_sections(self.current_chunk()))

        if self._current_sections:
            next_section = self._current_sections.pop(0)
            self.processed_size += len(next_section)
            self.update_progressbar()
            return next_section
        else:
            # if current list of sections is empty, look for more content
            # this will raise stop iteration at end of content
            self.get_next_chunk()
            self._current_sections = list(binarycontent_sections(self.current_chunk()))
            return self.get_next_section()

    def get_datastream_info(self, dsinfo):
        '''Use regular expressions to pull datastream [version]
        details (id, mimetype, size, and checksum) for binary content,
        in order to sanity check the decoded data.

        :param dsinfo: text content just before a binaryContent tag
        :returns: dict with keys for id, mimetype, size, type and digest,
            or None if no match is found
        '''
        # we only need to look at the end of this section of content
        dsinfo = dsinfo[-400:]
        # if not enough content is present, include the end of
        # the last read chunk, if available
        if len(dsinfo) < 400 and self.end_of_last_chunk is not None:
            dsinfo = self.end_of_last_chunk + dsinfo

        # force text needed for python 3 compatibility (in python 3
        # dsinfo is bytes instead of a string)
        try:
            text = force_text(dsinfo)
        except UnicodeDecodeError as err:
            # it's possible to see a unicode character split across
            # read blocks; if we get an "invalid start byte" unicode
            # decode error, try converting the text without the first
            # character; if that's the problem, it's not needed
            # for datastream context
            if 'invalid start byte' in force_text(err):
                text = force_text(dsinfo[1:])
            else:
                raise err

        infomatch = self.dsinfo_regex.search(text)
        if infomatch:
            return infomatch.groupdict()


    def update_progressbar(self):
        # update progressbar if we have one
        if self.progress_bar is not None:
            # progressbar doesn't like it when size exceeds maxval,
            # but we don't actually know maxval; adjust the maxval up
            # when necessary
            if self.progress_bar.max_value < self.processed_size:
                self.progress_bar.max_value = self.processed_size
            self.progress_bar.update(self.processed_size)


    def object_data(self):
        '''Process the archival export and return a buffer with foxml
        content for ingest into the destination repository.

        :returns: :class:`io.BytesIO` for ingest, with references
            to uploaded datastream content or content location urls
        '''
        self.foxml_buffer = io.BytesIO()

        if self.progress_bar:
            self.progress_bar.start()

        previous_section = None
        while True:
            try:
                section = self.get_next_section()
            except StopIteration:
                break

            if section == BINARY_CONTENT_START:
                self.within_file = True

                # get datastream info from the end of the section just before this one
                # (needed to provide size to upload request)
                dsinfo = self.get_datastream_info(previous_section)
                if dsinfo:
                    'Found encoded datastream %(id)s (%(mimetype)s, size %(size)s, %(type)s %(digest)s)' %  \
                        dsinfo

                    logger.info('Found encoded datastream %(id)s (%(mimetype)s, size %(size)s, %(type)s %(digest)s)',
                        dsinfo)
                else:
                    # error if datastream info is not found, because either
                    # size or version date is required to handle content
                    raise Exception('Failed to find datastream information for %s from \n%s' \
                        % (self.obj.pid, previous_section))

                if self.xml_only and not dsinfo['mimetype'] == 'text/xml':  # possibly others?
                    try:
                        dsid, dsversion = dsinfo['id'].split('.')
                    except ValueError:
                        # if dsid doesn't include a .# (for versioning),
                        # use the id as is.
                        dsid = dsinfo['id']

                    if self.url_credentials:
                        # if url credentials are set, parse the base fedora api
                        # url so they can be inserted at the right place
                        parsed_url = urlparse(self.obj.api.base_url)
                        # reassemble base url, adding in credentials
                        base_url = ''.join([parsed_url.scheme, '://',
                            self.url_credentials, parsed_url.netloc,
                            parsed_url.path])
                    else:
                        base_url = self.obj.api.base_url

                    # versioned datastream dissemination url
                    content_location = '%sobjects/%s/datastreams/%s/content?asOfDateTime=%s' % \
                        (base_url, self.obj.pid, dsid, dsinfo['created'])
                else:
                    upload_args = {}
                    if self.progress_bar:
                        def upload_callback(monitor):
                            self.progress_bar.upload = monitor.bytes_read
                        upload_args = {'callback': upload_callback}

                    # use upload id as content location
                    content_location = self.dest_repo.api.upload(self.encoded_datastream(),
                        size=int(dsinfo['size']), **upload_args)

                self.foxml_buffer.write(force_bytes('<foxml:contentLocation REF="%s" TYPE="URL"/>' \
                    % content_location))

            elif section == BINARY_CONTENT_END:
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
            if content == BINARY_CONTENT_END:
                if self.verify:
                    logger.info('Decoded content size %s (%s) MD5 %s',
                        size, humanize_file_size(size), md5.hexdigest())

                self.within_file = False

            elif self.within_file:
                content[:50]
                # if there was leftover binary content from the last chunk,
                # add it to the content now
                if leftover is not None:
                    content = b''.join([leftover, content])
                    leftover = None

                try:
                    # decode method used by base64.decode
                    decoded_content = binascii.a2b_base64(content)
                except binascii.Error:
                    # decoding can fail with a padding error when
                    # a line of encoded content runs across a read chunk
                    lines = content.split(b'\n')
                    # decode and yield all but the last line of encoded content
                    decoded_content = binascii.a2b_base64(b''.join(lines[:-1]))
                    # store the leftover to be decoded with the next chunk
                    leftover = lines[-1]

                if self.verify:
                    md5.update(decoded_content)

                size += len(decoded_content)
                yield decoded_content


def binarycontent_sections(chunk):
    '''Split a chunk of data into sections by start and end binary
    content tags.'''
    # using string split because it is significantly faster than regex.

    # use common text of start and end tags to split the text
    # (i.e. without < or </ tag beginning)
    binary_content_tag = BINARY_CONTENT_START[1:]
    if not binary_content_tag in chunk:
        # if no tags are present, don't do any extra work
        yield chunk

    else:
        # split on common portion of foxml:binaryContent
        sections = chunk.split(binary_content_tag)
        for sec in sections:
            extra = b''
            # check the end of the section to determine start/end tag
            if sec.endswith(b'</'):
                extra = sec[-2:]
                yield sec[:-2]

            elif sec.endswith(b'<'):
                extra = sec[-1:]
                yield sec[:-1]

            else:
                yield sec

            if extra:
                # yield the actual binary content tag
                # (delimiter removed by split, but needed for processing)
                yield b''.join([extra, binary_content_tag])


def estimate_object_size(obj, archive=True):
    '''Calculate a rough estimate of object size, based on the sizes of
    all versions of all datastreams.  If archive is true, adjusts
    the size estimate of managed datastreams for base64 encoded data.
    '''
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

def endswith_partial(text, partial_str):
    '''Check if the text ends with any partial version of the
    specified string.'''
    # at the end of the content
    # we don't care about complete overlap, so start checking
    # for matches without the last character
    test_str = partial_str[:-1]
    # look for progressively smaller segments
    while test_str:
        if text.endswith(test_str):
            return len(test_str)
        test_str = test_str[:-1]
    return False

