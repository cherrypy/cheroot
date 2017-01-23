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
