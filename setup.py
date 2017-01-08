import io

import setuptools


###############################################################################
# arguments for the setup command
###############################################################################
name = 'cheroot'
desc = 'Highly-optimized, pure-python HTTP server'

with io.open('README.rst', encoding='utf-8') as strm:
    long_desc = strm.read()

classifiers = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Web Environment',
    'Intended Audience :: Developers',
    'Operating System :: OS Independent',
    'Framework :: CherryPy',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.1',
    'Programming Language :: Python :: 3.2',
    'Programming Language :: Python :: 3.3',
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
]
author = 'CherryPy Team'
author_email = 'team@cherrypy.org'
url = 'http://www.cherrypy.org'
packages = [
    'cheroot', 'cheroot.test',
]

install_requires = [
    'six',
]

extras_require = {
    'testing': [
        'pytest',
        'backports.unittest_mock',
        'nose',
    ],
}
"""Feature flags end-users can use in dependencies"""

###############################################################################
# end arguments for setup
###############################################################################

params = dict(
    name=name,
    use_scm_version=True,
    description=desc,
    long_description=long_desc,
    classifiers=classifiers,
    author=author,
    author_email=author_email,
    url=url,
    packages=packages,
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    setup_requires=[
        'setuptools_scm',
    ],
    python_requires='>=2.6,!=3.0.*',
)


def main():
    setuptools.setup(**params)


if __name__ == '__main__':
    main()
