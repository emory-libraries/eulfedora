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
import re


def estimate_object_size(obj):
    # calculate rough estimate of object size
    size_estimate = 250000   # initial rough estimate for foxml size
    for ds in obj.ds_list:
        dsobj = obj.getDatastreamObject(ds)
        for version in dsobj.history().versions:
            size_estimate += version.size

    # TODO: optionally support calculating base64 encoded size

    return size_estimate




class ArchiveExport(object):

    # regex to match start or end of binary content
    bincontent_regex = re.compile('(</?foxml:binaryContent>)')
    # regex to pull out datastream version information
    dsinfo_regex = re.compile('ID="(?P<id>[^"]+)".*MIMETYPE="(?P<mimetype>[^"]+)".*SIZE="(?P<size>\d+)".* TYPE="(?P<type>[^"]+)".*DIGEST="(?P<digest>[0-9a-f]+)"',
        flags=re.MULTILINE|re.DOTALL)


    def __init__(self, obj, dest_repo):
        self.obj = obj
        self.dest_repo = dest_repo


    _export_response = None
    def get_export(self):
        if self._export_response is None:
            self._export_response = self.obj.api.export(self.obj.pid,
                context='archive', stream=True)
        return self._export_response

    _iter_content = None
    def export_iterator(self):
        if self._iter_content is None:
            # self._iter_content = self.get_export().iter_content(2048)  # testing, to exaggerate problems
            self._iter_content = self.get_export().iter_content(4096*1024*1024)
        return self._iter_content

    _current_chunk = None
    def current_chunk(self):
        return self._current_chunk

    partial_chunk = False

    def get_next_chunk(self):
        self.partial_chunk = False
        if self._iter_content is None:
            self.export_iterator()

        if self._current_chunk is not None:
            self.end_of_last_chunk = self._current_chunk[-200:]

        self._current_chunk = self._iter_content.next()
        return self._current_chunk

    def has_binary_content(self, chunk):
        # i.e., includes a start or end binary content tag
        return self.bincontent_regex.search(chunk)

    # _section_enumerate = None
    # def current_chunk_sections(self):
    #     sections = self.bincontent_regex.split(self.current_chunk())
    #     self._section_enumerate = enumerate(sections)
    #     return self._section_enumerate

    # def get_next_chunk_section(self):
    #     if self._section_enumerate is not None:
    #         return self._section_enumerate.next()
    end_of_last_chunk = None

    def data(self):
        # generator that can be used to upload to fedoro
        # response = self.obj.api.export(self.obj.pid, context='archive', stream=True)
        size = 0
        for chunk in self.export_iterator():
            size += len(chunk)

            # check if this chunk includes start or end of binary content
            if self.has_binary_content(chunk):
                # split into chunks based on binary content tags
                # NOTE: could contain multiple small binary content
                # sections in a single chunk
                subsections = self.bincontent_regex.split(chunk)

                for section in self.process_chunk_sections(subsections):
                    yield section

                if self.partial_chunk:
                    subsections = self.bincontent_regex.split(self.current_chunk())
                    for section in self.process_chunk_sections(subsections[self.section_start_idx:]):
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

            # error; ignoring for now
            # # update progressbar if we have one
            # if pbar:
            #     # progressbar doesn't like it when size exceeds maxval,
            #     # but we don't actually know maxval; adjust the maxval up
            #     # when necessary
            #     if pbar.maxval < size:
            #         pbar.maxval = size
            #     pbar.update(size)


    def process_chunk_sections(self, subsections):
        in_file = False
        for idx, content in enumerate(subsections):
            if content == '<foxml:binaryContent>':
                # FIXME: this can be simpler: it's either the second chunk after this one
                # OR data spans multiple chunks
                try:
                    if subsections[idx + 2] == '</foxml:binaryContent>':
                        end_index = idx + 2
                except IndexError:
                    end_index = None
                # print subsections[idx-1][-250:]
                # get datastream info from section immediately before
                dsinfo = subsections[idx-1][-250:]
                if len(dsinfo) < 250 and idx == 1:
                    dsinfo = self.end_of_last_chunk + dsinfo

                # print len(subsections[idx-1][-450:]), subsections[idx-1][-450:]
                # infomatch = self.dsinfo_regex.search(subsections[idx-1][-250:])
                infomatch = self.dsinfo_regex.search(dsinfo)
                if infomatch:
                    # print infomatch.groupdict()
                    print 'Found encoded datastream %(id)s (%(mimetype)s, size %(size)s, %(type)s %(digest)s)' \
                        % infomatch.groupdict()

                in_file = True
                # data = binary_data(subsections[idx+1:], resp_content)
                # print 'file data = ', ''.join(data)

                if end_index is None:
                    datasections = subsections[idx+1:]
                else:
                    datasections = subsections[idx+1:end_index+1]
                datagen = self.encoded_datastream(datasections)

                upload_id = self.dest_repo.api.upload(ReadableGenerator(datagen,
                    size=infomatch.groupdict()['size']),
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
    def encoded_datastream(self, sections, size=0, md5=None, leftover=None):
        # return a generator of data to be uploaded to fedora
        found_end = False
        if md5 is None:
            md5 = hashlib.md5()
        for idx, content in enumerate(sections):
            if content == '</foxml:binaryContent>':
                print 'total size %s md5 %s' % (size, md5.hexdigest())
                found_end = True
            elif not found_end:
                # decode method used by base64.decode
                # print 'content beginning = ', content[:200]
                if leftover is not None:
                    content = ''.join([leftover, content])
                    leftover = None
                    # print 'content beginning with leftover = ', content[:200]

                try:
                    decoded_content = binascii.a2b_base64(content)
                    # TODO: if padding is incorrect, needs to grab
                    # next chunk before it can be decoded

                except binascii.Error as berr:
                    # print 'decode error ', berr
                    # print content[-200:]
                    # decoding can fail with a padding error when
                    # a line of b64 encoded content runs across a read chunk
                    lines = content.split('\n')
                    # decode and yield all but the last line of encoded content
                    # decoded_content = binascii.a2b_base64('\n'.join(lines[:-1]))
                    # store the leftover to decode with the next chunk
                    leftover = lines[-1]
                    # print 'leftover = ', leftover

                    decoded_content = binascii.a2b_base64(''.join(lines[:-1]))
                    # print len(decoded_content), ' - len decoded all but last line'

                md5.update(decoded_content)
                size += len(decoded_content)
                # print 'decoded content = ', decoded_content
                yield decoded_content
            else:
                # set a flag
                self.partial_chunk = True
                self.section_start_idx = idx
                # stop processing
                break

        # if end was not found in current chunk, get next chunk
        # and keep going
        if not found_end:
            chunk = self.get_next_chunk()
            subsections = self.bincontent_regex.split(chunk)
            for data in self.encoded_datastream(subsections, size=size,
                                                md5=md5, leftover=leftover):
                yield data


class ReadableGenerator(object):
    def __init__(self, gen, size):
        self.gen = gen
        self.size = size
    def read(self, size=None):
        if size is None:
            # FIXME: doesn't this defeat the purpose of the generator?
            return ''.join(self.gen)
        print 'read size requested = ', size
        # todo: handle size
        # while self.gen.next()
    def __len__(self):
        return int(self.size)


