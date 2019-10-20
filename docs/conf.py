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
    'scm_tag_titles_ext',
]

master_doc = 'index'

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

nitpicky = True

# NOTE: consider having a separate ignore file
# Ref: https://stackoverflow.com/a/30624034/595220
nitpick_ignore = [
    ('py:const', 'socket.SO_PEERCRED'),
    ('py:class', '_pyio.BufferedWriter'),
    ('py:class', '_pyio.BufferedReader'),
    ('py:class', 'unittest.case.TestCase'),
]
