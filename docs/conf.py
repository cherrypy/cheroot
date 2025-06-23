# pylint: disable=invalid-name
"""Configuration of Sphinx documentation generator."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# -- Path setup --------------------------------------------------------------

PROJECT_ROOT_DIR = Path(__file__).parents[1].resolve()
IS_RELEASE_ON_RTD = (
    os.getenv('READTHEDOCS', 'False') == 'True'
    and os.environ['READTHEDOCS_VERSION_TYPE'] == 'tag'
)
if IS_RELEASE_ON_RTD:
    tags: set[str]
    # pylint: disable-next=used-before-assignment
    tags.add('is_release')  # noqa: F821


# Make in-tree extension importable in non-tox setups/envs, like RTD.
# Refs:
# https://github.com/readthedocs/readthedocs.org/issues/6311
# https://github.com/readthedocs/readthedocs.org/issues/7182
sys.path.insert(0, str(PROJECT_ROOT_DIR))


extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosectionlabel',  # autocreate section targets for refs
    'sphinx.ext.doctest',
    'sphinx.ext.extlinks',
    'sphinx.ext.intersphinx',
    # Third-party extensions:
    'jaraco.packaging.sphinx',
    'sphinx_tabs.tabs',
    'sphinxcontrib.apidoc',
    'sphinxcontrib.towncrier.ext',  # provides `.. towncrier-draft-entries::`
    # In-tree extensions:
    'spelling_stub_ext',  # auto-loads `sphinxcontrib.spelling` if installed
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = [
    'changelog-fragments.d/**',  # Towncrier-managed change notes
]

master_doc = 'index'

apidoc_excluded_paths = []
apidoc_extra_args = [
    '--implicit-namespaces',
    '--private',  # include “_private” modules
]
apidoc_module_dir = '../cheroot'
apidoc_module_first = False
apidoc_output_dir = 'pkg'
apidoc_separate_modules = True
apidoc_toc_file = None

spelling_ignore_acronyms = True
spelling_ignore_importable_modules = True
# PyPI lookup because of https://github.com/sphinx-contrib/spelling/issues/227
spelling_ignore_pypi_package_names = False
spelling_ignore_python_builtins = True
spelling_ignore_wiki_words = True
spelling_show_suggestions = True
spelling_word_list_filename = [
    'spelling_wordlist.txt',
]

github_url = 'https://github.com'
github_repo_org = 'cherrypy'
github_repo_name = 'cheroot'
github_repo_slug = f'{github_repo_org}/{github_repo_name}'
github_repo_url = f'{github_url}/{github_repo_slug}'
cp_github_repo_url = f'{github_url}/{github_repo_org}/cherrypy'
github_sponsors_url = f'{github_url}/sponsors'

extlinks = {
    'issue': (f'{github_repo_url}/issues/%s', '#%s'),
    'pr': (f'{github_repo_url}/pull/%s', 'PR #%s'),
    'commit': (f'{github_repo_url}/commit/%s', '%s'),
    'cp-issue': (f'{cp_github_repo_url}/issues/%s', 'CherryPy #%s'),
    'cp-pr': (f'{cp_github_repo_url}/pull/%s', 'CherryPy PR #%s'),
    'gh': (f'{github_url}/%s', 'GitHub: %s'),
    'user': (f'{github_sponsors_url}/%s', '@%s'),
}

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'python2': ('https://docs.python.org/2', None),
    # Ref: https://github.com/cherrypy/cherrypy/issues/1872
    'cherrypy': (
        'https://docs.cherrypy.dev/en/latest',
        ('https://cherrypy.rtfd.io/en/latest', None),
    ),
    'trustme': ('https://trustme.readthedocs.io/en/latest/', None),
    'ddt': ('https://ddt.readthedocs.io/en/latest/', None),
    'pyopenssl': ('https://www.pyopenssl.org/en/latest/', None),
    'towncrier': ('https://towncrier.rtfd.io/en/latest', None),
}

linkcheck_ignore = [
    r'http://localhost:\d+/',  # local URLs
    r'https://codecov\.io/gh/cherrypy/cheroot/branch/master/graph/badge\.svg',
    r'https://github\.com/cherrypy/cheroot/actions',  # 404 if no auth
    # Too many links to GitHub so they cause
    # "429 Client Error: too many requests for url"
    # Ref: https://github.com/sphinx-doc/sphinx/issues/7388
    r'https://github\.com/cherrypy/cheroot/commit'
    r'https://github\.com/cherrypy/cheroot/issues',
    r'https://github\.com/cherrypy/cheroot/pull',
    r'https://github\.com/cherrypy/cherrypy/commit'
    r'https://github\.com/cherrypy/cherrypy/issues',
    r'https://github\.com/cherrypy/cherrypy/pull',
    # Has an ephemeral anchor (line-range) but actual HTML has separate per-
    # line anchors.
    r'https://github\.com'
    r'/python/cpython/blob/c39b52f/Lib/poplib\.py#L297-L302',
    r'https://github\.com'
    r'/python/cpython/blob/c39b52f/Lib/poplib\.py#user-content-L297-L302',
    r'^https://img\.shields\.io/matrix',  # these are rate-limited
    r'^https://matrix\.to/#',  # these render fully on front-end from anchors
    r'^https://stackoverflow\.com/',  # these generate HTTP 403 Forbidden
    r'^https://forums\.sabnzbd\.org/',  # these generate HTTP 403 Forbidden
]
linkcheck_anchors_ignore = [
    r'^!',  # default
    # ignore anchors that start with a '/', e.g. Wikipedia media files:
    # https://en.wikipedia.org/wiki/Walrus#/media/File:Pacific_Walrus_-_Bull_(8247646168).jpg
    r'\/.*',
    r'issuecomment-\d+',  # GitHub comments
]
linkcheck_workers = 25

# -- Options for sphinx.ext.autosectionlabel extension -----------------------

# Ref:
# https://www.sphinx-doc.org/en/master/usage/extensions/autosectionlabel.html
autosectionlabel_maxdepth = 1  # mitigate Towncrier nested subtitles collision

nitpicky = True

# NOTE: consider having a separate ignore file
# Ref: https://stackoverflow.com/a/30624034/595220
nitpick_ignore = [
    ('py:const', 'socket.SO_PEERCRED'),
    ('py:class', '_pyio.BufferedWriter'),
    ('py:class', '_pyio.BufferedReader'),
    ('py:class', 'unittest.case.TestCase'),
    ('py:meth', 'cheroot.connections.ConnectionManager.get_conn'),
    # Ref: https://github.com/pyca/pyopenssl/issues/1012
    ('py:class', 'pyopenssl:OpenSSL.SSL.Context'),
]

# -- Options for towncrier_draft extension -----------------------------------

# or: 'sphinx-version', 'sphinx-release'
towncrier_draft_autoversion_mode = 'draft'
towncrier_draft_include_empty = True
towncrier_draft_working_directory = PROJECT_ROOT_DIR
towncrier_draft_config_path = 'towncrier.toml'  # relative to cwd


# Ref:
# * https://github.com/djungelorm/sphinx-tabs/issues/26#issuecomment-422160463
sphinx_tabs_valid_builders = ['linkcheck']  # prevent linkcheck warning


# Ref: https://github.com/python-attrs/attrs/pull/571/files\
#      #diff-85987f48f1258d9ee486e3191495582dR82
default_role = 'any'


html_theme = 'furo'
