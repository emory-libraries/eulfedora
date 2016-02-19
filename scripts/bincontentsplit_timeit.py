from timeit import timeit
import re

# test regex split vs string for binary content

def get_data():
    sync1_export = 'test/test_fedora/fixtures/synctest1-export.xml'
    sync2_export = 'test/test_fedora/fixtures/synctest2-export.xml'
    # with open(sync1_export) as exportcontent:
    with open(sync2_export) as exportcontent:
        return exportcontent.read()


def regex_split():
    bincontent_regex = re.compile(r'(</?foxml:binaryContent>)')
    bincontent_regex.split(get_data())


def string_split():
    sections = get_data().split('foxml:binaryContent>')
    def gen():
        last = len(sections)
        for idx, sec in enumerate(sections):
            if sec.endswith('</'):
                yield sec[:-2]
                extra = sec[-2:]
            elif sec.endswith('<'):
                yield sec[:-1]
                extra = sec[-1:]
            if idx != last:
                yield ''.join([extra, 'foxml:binaryContent>'])
    list(gen())
    # print '%d sections' % len(sections)

# def string_split_or():

#     def tween(seq, sep):
#         return reduce(lambda r,v: r+[sep,v], seq[1:], seq[:1])

#     sections = get_data().split('<foxml:binaryContent>')

#     sections = tween(split2 for sec in tween(sections, '<foxml:binaryContent>')
#                         for split2 in sec.split('</foxml:binaryContent>'),
#                         '</foxml:binaryContent>')

    # print '%d sections' % len(list(sections))



def str_replace_split():
    sections = get_data().replace('</foxml:binaryContent>', '<foxml:binaryContent>') \
        .split('foxml:binaryContent>')
    # print '%d sections' % len(sections)


def split_and_keep():
    text = get_data()

    # Find replacement character that is not used in string
    # i.e. just use the highest available character plus one
    # Note: This fails if ord(max(s)) = 0x10FFFF (ValueError)
    marker = chr(ord(max(text))+1)
    text.replace('foxml:binaryContent>', 'foxml:binaryContent>%s' % marker) \
        .replace('<foxml:binaryContent>', '%s<foxml:binaryContent>' % marker) \
        .replace('</foxml:binaryContent>', '%s</foxml:binaryContent>' % marker) \
        .split(marker)


def split_and_intersperse():
    BINARY_CONTENT_START = '<foxml:binaryContent>'
    #: foxml binary content end tag
    BINARY_CONTENT_END = '</foxml:binaryContent>'
    chunk = get_data()
    def gen():
        for idx, section in enumerate(chunk.split(BINARY_CONTENT_START)):
            if idx != 0:
                yield BINARY_CONTENT_START
            if BINARY_CONTENT_END in section:
                for subidx, subsect in enumerate(section.split(BINARY_CONTENT_END)):
                    if subidx != 0:
                        yield BINARY_CONTENT_END
                    yield subsect
            else:
                yield section
    list(gen())

# print timeit("regex_split()", "from __main__ import regex_split")
print timeit("string_split()", "from __main__ import string_split")
# print timeit("string_split_or()", "from __main__ import string_split_or")
# print timeit("str_replace_split()", "from __main__ import str_replace_split")
# print timeit("split_and_keep()", "from __main__ import split_and_keep")
# print timeit("split_and_intersperse()", "from __main__ import split_and_intersperse")
# print timeit("re_find(string, text)", "from __main__ import regex_split; string='lookforme'; text='look'")


'''
sync1 export results:
- regex: 160.252336979
- split: 24.0797049999
- split or: 24.6915950775
- replace/split: 36.1867218018

string split or with tween: 553.95399189  ouch!

split and intersperse:  39.6330699921

sync2 export results
- regex: 306.168256044
- split: 34.1267879009
- split or: 35.5764200687
- replace/split: 59.8450729847


split and intersperse: 58.6153240204
'''
