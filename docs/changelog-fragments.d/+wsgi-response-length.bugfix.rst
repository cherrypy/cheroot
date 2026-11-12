Fixed enforcement of ``Content-Length`` across multiple chunks returned by WSGI applications, including calls to the ``write()`` callable.
