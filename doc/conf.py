# eulcore documentation build configuration file

import eulfedora

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx']

templates_path = ['templates']
exclude_trees = ['build']
source_suffix = '.rst'
master_doc = 'index'

project = 'eulfedora'
copyright = '2011, Emory University Libraries'
version = '%d.%d' % eulfedora.__version_info__[:2]
release = eulfedora.__version__
modindex_common_prefix = ['eulfedora.']

pygments_style = 'sphinx'

html_static_path = ['_static']
htmlhelp_basename = 'eulfedora'

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'alabaster'
html_style = 'style.css'
html_theme_options = {
    # 'logo': 'logo.png',
    'github_user': 'emory-libraries',
    'github_repo': 'eulfedora',
    # 'travis_button': True,  # enable when we get travis-ci set up
    'description': 'Pythonic access to Fedora Commons 3.x repositories'
    # 'analytics_id':
}

html_sidebars = {
    '**': ['about.html', 'navigation.html',
          'searchbox.html', 'sidebar_footer.html'],
}

latex_documents = [
  ('index', 'eulcore.tex', 'eulfedora Documentation',
   'Emory University Libraries', 'manual'),
]

# configuration for intersphinx: refer to the Python standard library, eulxml, django
intersphinx_mapping = {
    'django': ('http://django.readthedocs.org/en/latest/', None),
    'eulcommon': ('http://eulcommon.readthedocs.org/en/latest/', None),
    'eulxml': ('http://eulxml.readthedocs.org/en/latest/', None),
    'python': ('http://docs.python.org/', None),
    'rdflib': ('http://rdflib.readthedocs.org/en/latest/', None),
    'requests': ('http://docs.python-requests.org/en/master/', None),
}
