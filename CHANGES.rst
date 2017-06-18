v5.5.2
======

- #32: Ignore "unknown error" and "https proxy request" SSL errors.

  Ref: sabnzbd/sabnzbd#820

  Ref: sabnzbd/sabnzbd#860

v5.5.1
======

- Make Appveyor list separate tests in corresponding tab.

- #29: Configure Travis CI build stages.

  Prioritize tests by stages.

  Move deploy stage to be run very last after all other stages finish.

- #31: Ignore "Protocol wrong type for socket" (EPROTOTYPE) @ OSX for non-blocking sockets.

  This was originally fixed for regular sockets in cherrypy/cherrypy#1392.

  Ref: https://forums.sabnzbd.org/viewtopic.php?f=2&t=22728&p=112251

v5.5.0
======

- #17 via #25: Instead of a read_headers function, cheroot now
  supplies a HeaderReader class to perform the same function.

  Any HTTPRequest object may override the header_reader attribute
  to customize the handling of incoming headers.

  The server module also presents a provisional implementation of
  a DropUnderscoreHeaderReader that will exclude any headers
  containing an underscore. It remains an exercise for the
  implementer to demonstrate how this functionality might be
  employed in a server such as CherryPy.

- #26: Configured TravisCI to run tests under OS X.

v5.4.0
======

#22: Add "ciphers" parameter to SSLAdapter.

v5.3.0
======

#8: Updated style to better conform to PEP 8.

Refreshed project with `jaraco skeleton
<https://github.com/jaraco/skeleton>`_.

Docs now built and `deployed at RTD
<http://cheroot.readthedocs.io/en/latest/history.html>`_.

v5.2.0
======

#5: Set `Server.version` to Cheroot version instead of CherryPy version.

#4: Prevent tracebacks and drop bad HTTPS connections in the
    ``BuiltinSSLAdapter``, similar to ``pyOpenSSLAdapter``.

#3: Test suite now runs and many tests pass. Some are still
    failing.

v5.1.0
======

Removed the WSGI prefix from classes in :module:`cheroot.wsgi`.
Kept aliases for compatibility.

#1: Corrected docstrings in :module:`cheroot.server`
and :module:`cheroot.wsgi`.

#2: Fixed ImportError when pkg_resources cannot find the
    cheroot distribution.

v5.0.1
======

Fix error in ``parse_request_uri`` created in 68a5769.

v5.0.0
======

Initial release based on cherrypy.cherrypy.wsgiserver 8.8.0.
