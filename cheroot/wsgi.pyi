import typing as _t

from . import server

class Server(server.HTTPServer):
    wsgi_version: _t.Any
    wsgi_app: _t.Any
    request_queue_size: _t.Any
    timeout: _t.Any
    shutdown_timeout: _t.Any
    requests: _t.Any
    def __init__(
        self,
        bind_addr,
        wsgi_app,
        numthreads: int = ...,
        server_name: _t.Any | None = ...,
        max: int = ...,
        request_queue_size: int = ...,
        timeout: int = ...,
        shutdown_timeout: int = ...,
        accepted_queue_size: int = ...,
        accepted_queue_timeout: int = ...,
        peercreds_enabled: bool = ...,
        peercreds_resolve_enabled: bool = ...,
        reuse_port: bool = ...,
    ) -> None: ...
    @property
    def numthreads(self): ...
    @numthreads.setter
    def numthreads(self, value) -> None: ...

class Gateway(server.Gateway):
    started_response: bool
    env: _t.Any
    remaining_bytes_out: _t.Any
    def __init__(self, req) -> None: ...
    @classmethod
    def gateway_map(cls): ...
    def get_environ(self) -> None: ...
    def respond(self) -> None: ...
    def start_response(
        self,
        status,
        headers,
        exc_info: _t.Any | None = ...,
    ): ...
    def write(self, chunk) -> None: ...

class Gateway_10(Gateway):
    version: _t.Any
    def get_environ(self): ...

class Gateway_u0(Gateway_10):
    version: _t.Any
    def get_environ(self): ...

wsgi_gateways: _t.Any

class PathInfoDispatcher:
    apps: _t.Any
    def __init__(self, apps): ...
    def __call__(self, environ, start_response): ...

WSGIServer = Server
WSGIGateway = Gateway
WSGIGateway_u0 = Gateway_u0
WSGIGateway_10 = Gateway_10
WSGIPathInfoDispatcher = PathInfoDispatcher
