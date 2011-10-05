# eulcore documentation build configuration file

import eulfedora

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx']

#templates_path = ['templates']
exclude_trees = ['build']
source_suffix = '.rst'
master_doc = 'index'

project = 'EULfedora'
copyright = '2011, Emory University Libraries'
version = '%d.%d' % eulfedora.__version_info__[:2]
release = eulfedora.__version__
modindex_common_prefix = ['eulfedora.']

pygments_style = 'sphinx'

html_style = 'default.css'
#html_static_path = ['static']
htmlhelp_basename = 'eulcoredoc'

latex_documents = [
  ('index', 'eulcore.tex', 'EULfedora Documentation',
   'Emory University Libraries', 'manual'),
]

# configuration for intersphinx: refer to the Python standard library, eulxml, django
intersphinx_mapping = {
    'django': ('http://django.readthedocs.org/en/latest/', None),
    'eulcommon': ('http://eulcommon.readthedocs.org/en/latest/', None),
    'eulxml': ('http://eulxml.readthedocs.org/en/latest/', None),
    'python': ('http://docs.python.org/', None),
}
