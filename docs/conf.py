#!/usr/bin/env python3
# Requires Python 3.6+
"""Configuration of Sphinx documentation generator."""

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.extlinks',
    'sphinx.ext.intersphinx',
    'jaraco.packaging.sphinx',
    'rst.linker',
]

master_doc = 'index'

link_files = {
    '../CHANGES.rst': dict(
        replace=[
            dict(
                pattern=r'^(?m)((?P<scm_version>v?\d+(\.\d+){1,2}))\n[-=]+\n',
                with_scm='{text}\n{rev[timestamp]:%d %b %Y}\n',
            ),
        ],
    ),
}

github_url = 'https://github.com'
github_repo_org = 'cherrypy'
github_repo_name = 'cheroot'
github_repo_slug = '{}/{}'.format(github_repo_org, github_repo_name)
github_repo_url = '{}/{}'.format(github_url, github_repo_slug)
cp_github_repo_url = '{}/{}/cherrypy'.format(github_url, github_repo_org)

extlinks = {
    'issue': ('{}/issues/%s'.format(github_repo_url), '#'),
    'pr': ('{}/pulls/%s'.format(github_repo_url), 'PR #'),
    'commit': ('{}/commit/%s'.format(github_repo_url), ''),
    'cp-issue': ('{}/issues/%s'.format(cp_github_repo_url), 'CherryPy #'),
    'cp-pr': ('{}/pulls/%s'.format(cp_github_repo_url), 'CherryPy PR #'),
    'gh': ('{}/%s'.format(github_url), 'GitHub: '),
}

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'cherrypy': ('http://docs.cherrypy.org/en/latest/', None),
}
