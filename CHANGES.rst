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
