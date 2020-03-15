#! /usr/bin/env python3
# Requires Python 3.6+
# pylint: disable=invalid-name
"""Configuration of Sphinx documentation generator."""

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.extlinks',
    'sphinx.ext.intersphinx',
    'jaraco.packaging.sphinx',
    'sphinx_tabs.tabs',
    'sphinxcontrib.spelling',
    'scm_tag_titles_ext',
]

master_doc = 'index'

spelling_ignore_acronyms = True
spelling_ignore_importable_modules = True
spelling_ignore_pypi_package_names = True
spelling_ignore_python_builtins = True
spelling_ignore_wiki_words = True
spelling_show_suggestions = True
spelling_word_list_filename = [
    'spelling_wordlist.txt',
]

scm_version_title_settings = {
    'scm': 'git',
    'date_format': '%d %b %Y',
}

github_url = 'https://github.com'
github_repo_org = 'cherrypy'
github_repo_name = 'cheroot'
github_repo_slug = f'{github_repo_org}/{github_repo_name}'
github_repo_url = f'{github_url}/{github_repo_slug}'
cp_github_repo_url = f'{github_url}/{github_repo_org}/cherrypy'

extlinks = {
    'issue': (f'{github_repo_url}/issues/%s', '#'),
    'pr': (f'{github_repo_url}/pull/%s', 'PR #'),
    'commit': (f'{github_repo_url}/commit/%s', ''),
    'cp-issue': (f'{cp_github_repo_url}/issues/%s', 'CherryPy #'),
    'cp-pr': (f'{cp_github_repo_url}/pull/%s', 'CherryPy PR #'),
    'gh': (f'{github_url}/%s', 'GitHub: '),
}

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'python2': ('https://docs.python.org/2', None),
    'cherrypy': ('https://docs.cherrypy.org/en/latest/', None),
    'trustme': ('https://trustme.readthedocs.io/en/latest/', None),
    'ddt': ('https://ddt.readthedocs.io/en/latest/', None),
    'pyopenssl': ('https://www.pyopenssl.org/en/latest/', None),
}

linkcheck_ignore = [
    r'http://localhost:\d+/',  # local URLs
    r'https://codecov\.io/gh/cherrypy/cheroot/branch/master/graph/badge\.svg',
    r'https://github\.com/cherrypy/cheroot/actions',  # 404 if no auth
    # Requires a more liberal 'Accept: ' HTTP request header:
    # Ref: https://github.com/sphinx-doc/sphinx/issues/7247
    r'https://github\.com/cherrypy/cheroot/workflows/[^/]+/badge\.svg',
]
linkcheck_workers = 25

nitpicky = True

# NOTE: consider having a separate ignore file
# Ref: https://stackoverflow.com/a/30624034/595220
nitpick_ignore = [
    ('py:const', 'socket.SO_PEERCRED'),
    ('py:class', '_pyio.BufferedWriter'),
    ('py:class', '_pyio.BufferedReader'),
    ('py:class', 'unittest.case.TestCase'),
]

# Ref:
# * https://github.com/djungelorm/sphinx-tabs/issues/26#issuecomment-422160463
sphinx_tabs_valid_builders = ['linkcheck']  # prevent linkcheck warning
