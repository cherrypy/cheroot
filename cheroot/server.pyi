from typing import Any

class HeaderReader:
    def __call__(self, rfile, hdict: Any | None = ...): ...

class DropUnderscoreHeaderReader(HeaderReader): ...

class SizeCheckWrapper:
    rfile: Any
    maxlen: Any
    bytes_read: int
    def __init__(self, rfile, maxlen) -> None: ...
    def read(self, size: Any | None = ...): ...
    def readline(self, size: Any | None = ...): ...
    def readlines(self, sizehint: int = ...): ...
    def close(self) -> None: ...
    def __iter__(self): ...
    def __next__(self): ...
    next: Any

class KnownLengthRFile:
    rfile: Any
    remaining: Any
    def __init__(self, rfile, content_length) -> None: ...
    def read(self, size: Any | None = ...): ...
    def readline(self, size: Any | None = ...): ...
    def readlines(self, sizehint: int = ...): ...
    def close(self) -> None: ...
    def __iter__(self): ...
    def __next__(self): ...
    next: Any

class ChunkedRFile:
    rfile: Any
    maxlen: Any
    bytes_read: int
    buffer: Any
    bufsize: Any
    closed: bool
    def __init__(self, rfile, maxlen, bufsize: int = ...) -> None: ...
    def read(self, size: Any | None = ...): ...
    def readline(self, size: Any | None = ...): ...
    def readlines(self, sizehint: int = ...): ...
    def read_trailer_lines(self) -> None: ...
    def close(self) -> None: ...

class HTTPRequest:
    server: Any
    conn: Any
    inheaders: Any
    outheaders: Any
    ready: bool
    close_connection: bool
    chunked_write: bool
    header_reader: Any
    started_request: bool
    scheme: bytes
    response_protocol: str
    status: str
    sent_headers: bool
    chunked_read: bool
    proxy_mode: Any
    strict_mode: Any
    def __init__(
        self, server, conn, proxy_mode: bool = ..., strict_mode: bool = ...
    ) -> None: ...
    rfile: Any
    def parse_request(self) -> None: ...
    uri: Any
    method: Any
    authority: Any
    path: Any
    qs: Any
    request_protocol: Any
    def read_request_line(self): ...
    def read_request_headers(self): ...
    def respond(self) -> None: ...
    def simple_response(self, status, msg: str = ...) -> None: ...
    def ensure_headers_sent(self) -> None: ...
    def write(self, chunk) -> None: ...
    def send_headers(self) -> None: ...

class HTTPConnection:
    remote_addr: Any
    remote_port: Any
    ssl_env: Any
    rbufsize: Any
    wbufsize: Any
    RequestHandlerClass: Any
    peercreds_enabled: bool
    peercreds_resolve_enabled: bool
    last_used: Any
    server: Any
    socket: Any
    rfile: Any
    wfile: Any
    requests_seen: int
    def __init__(self, server, sock, makefile=...) -> None: ...
    def communicate(self): ...
    linger: bool
    def close(self) -> None: ...
    def get_peer_creds(self): ...
    @property
    def peer_pid(self): ...
    @property
    def peer_uid(self): ...
    @property
    def peer_gid(self): ...
    def resolve_peer_creds(self): ...
    @property
    def peer_user(self): ...
    @property
    def peer_group(self): ...

class HTTPServer:
    gateway: Any
    minthreads: Any
    maxthreads: Any
    server_name: Any
    protocol: str
    request_queue_size: int
    shutdown_timeout: int
    timeout: int
    expiration_interval: float
    version: Any
    software: Any
    ready: bool
    max_request_header_size: int
    max_request_body_size: int
    nodelay: bool
    ConnectionClass: Any
    ssl_adapter: Any
    peercreds_enabled: bool
    peercreds_resolve_enabled: bool
    reuse_port: bool
    keep_alive_conn_limit: int
    requests: Any
    def __init__(
        self,
        bind_addr,
        gateway,
        minthreads: int = ...,
        maxthreads: int = ...,
        server_name: Any | None = ...,
        peercreds_enabled: bool = ...,
        peercreds_resolve_enabled: bool = ...,
        reuse_port: bool = ...,
    ) -> None: ...
    stats: Any
    def clear_stats(self): ...
    def runtime(self): ...
    @property
    def bind_addr(self): ...
    @bind_addr.setter
    def bind_addr(self, value) -> None: ...
    def safe_start(self) -> None: ...
    socket: Any
    def prepare(self) -> None: ...
    def serve(self) -> None: ...
    def start(self) -> None: ...
    @property
    def can_add_keepalive_connection(self): ...
    def put_conn(self, conn) -> None: ...
    def error_log(
        self, msg: str = ..., level: int = ..., traceback: bool = ...
    ) -> None: ...
    def bind(self, family, type, proto: int = ...): ...
    def bind_unix_socket(self, bind_addr): ...
    @staticmethod
    def _make_socket_reusable(socket_, bind_addr) -> None: ...
    @classmethod
    def prepare_socket(
        cls,
        bind_addr,
        family,
        type,
        proto,
        nodelay,
        ssl_adapter,
        reuse_port: bool = ...,
    ): ...
    @staticmethod
    def bind_socket(socket_, bind_addr): ...
    @staticmethod
    def resolve_real_bind_addr(socket_): ...
    def process_conn(self, conn) -> None: ...
    @property
    def interrupt(self): ...
    @interrupt.setter
    def interrupt(self, interrupt) -> None: ...
    def stop(self) -> None: ...

class Gateway:
    req: Any
    def __init__(self, req) -> None: ...
    def respond(self) -> None: ...

def get_ssl_adapter_class(name: str = ...): ...
