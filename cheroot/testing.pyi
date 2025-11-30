import typing as _t

from .server import HTTPServer
from .wsgi import Server

T = _t.TypeVar('T', bound=HTTPServer)

EPHEMERAL_PORT: int
NO_INTERFACE: str | None
ANY_INTERFACE_IPV4: str
ANY_INTERFACE_IPV6: str
config: dict

def cheroot_server(server_factory: T) -> _t.Iterator[T]: ...
def wsgi_server() -> _t.Iterator[Server]: ...
def native_server() -> _t.Iterator[HTTPServer]: ...
def get_server_client(server) -> _t.Any: ...
