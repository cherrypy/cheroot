#! /usr/bin/env python
"""Cheroot package setuptools installer."""

# Project skeleton maintained at https://github.com/jaraco/skeleton

import io

import setuptools

with io.open('README.rst', encoding='utf-8') as readme:
    long_description = readme.read()

name = 'cheroot'
description = 'Highly-optimized, pure-python HTTP server'
nspkg_technique = 'native'
"""
Does this package use "native" namespace packages or
pkg_resources "managed" namespace packages?
"""

repo_slug = 'cherrypy/{}'.format(name)
repo_url = 'https://github.com/{}'.format(repo_slug)

params = dict(
    name=name,
    use_scm_version=True,
    author='CherryPy Team',
    author_email='team@cherrypy.org',
    description=description or name,
    long_description=long_description,
    url=repo_url,
    project_urls={
        'CI: AppVeyor': 'https://ci.appveyor.com/project/{}'.format(repo_slug),
        'CI: Travis': 'https://travis-ci.org/{}'.format(repo_slug),
        'CI: Circle': 'https://circleci.com/gh/{}'.format(repo_slug),
        'Docs: RTD': 'https://{}.cherrypy.org'.format(name),
        'GitHub: issues': '{}/issues'.format(repo_url),
        'GitHub: repo': repo_url,
    },
    packages=setuptools.find_packages(),
    include_package_data=True,
    namespace_packages=(
        name.split('.')[:-1] if nspkg_technique == 'managed'
        else []
    ),
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*',
    install_requires=[
        'backports.functools_lru_cache',
        'six>=1.11.0',
        'more_itertools>=2.6',
    ],
    extras_require={
        'docs': [
            'sphinx',
            'rst.linker>=1.9',
            'jaraco.packaging>=3.2',

            'docutils',
            'alabaster',

            'collective.checkdocs',
        ],
        'testing': [
            'pytest>=2.8',
            'pytest-sugar',
            'pytest-testmon>=0.9.7',
            'pytest-watch',

            # measure test coverage
            'coverage',
            # send test coverage to codecov.io
            'codecov',

            'pytest-cov',
            'backports.unittest_mock',
        ],
    },
    setup_requires=[
        'setuptools_scm>=1.15.0',
        'setuptools_scm_git_archive>=1.0',
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Framework :: CherryPy',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: Jython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Server',
    ],
    entry_points={
        'console_scripts': [
            'cheroot = cheroot.cli:main',
        ],
    },
)
if __name__ == '__main__':
    setuptools.setup(**params)
