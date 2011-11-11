#!/usr/bin/env python

# file test_indexdata/test_util.py
# 
#   Copyright 2011 Emory University Libraries
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

import unittest
import os

# must be set before importing anything from django
os.environ['DJANGO_SETTINGS_MODULE'] = 'testsettings'

from django.conf import settings
from django.test import TestCase

from eulfedora.models import DigitalObject, FileDatastream
from eulfedora.server import Repository

from eulfedora.indexdata.util import pdf_to_text


class TestPdfObject(DigitalObject):
    pdf = FileDatastream("PDF", "PDF document", defaults={
        	'versionable': False, 'mimetype': 'application/pdf'
        })


class PdfToTextTest(unittest.TestCase):
    fixture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
    pdf_filepath = os.path.join(fixture_dir, 'test.pdf')
    pdf_text = 'This is a short PDF document to use for testing.'

    def setUp(self):
        self.repo = Repository(settings.FEDORA_ROOT, settings.FEDORA_USER,
                               settings.FEDORA_PASSWORD)
        with open(self.pdf_filepath) as pdf:
            self.pdfobj = self.repo.get_object(type=TestPdfObject)
            self.pdfobj.label = 'eulindexer test pdf object'
            self.pdfobj.pdf.content = pdf
            self.pdfobj.save()

    def tearDown(self):
        self.repo.purge_object(self.pdfobj.pid)
        
    def test_file(self):
        # extract text from a pdf from a file on the local filesystem
        text = pdf_to_text(open(self.pdf_filepath, 'rb'))
        self.assertEqual(self.pdf_text, text)

    def test_object_datastream(self):
        # extract text from a pdf datastream in fedora
        pdfobj = self.repo.get_object(self.pdfobj.pid, type=TestPdfObject)
        text = pdf_to_text(pdfobj.pdf.content)
        self.assertEqual(self.pdf_text, text)
