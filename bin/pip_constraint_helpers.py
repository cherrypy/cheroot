"""Shared functions for platform detection."""

from __future__ import annotations

import pathlib
import platform
import shlex
import subprocess  # noqa: S404 -- pip/pip-tools don't have importable APIs
import sys


PYTHON_IMPLEMENTATION_MAP = {  # noqa: WPS407
    'cpython': 'cp',
    'ironpython': 'ip',
    'jython': 'jy',
    'python': 'py',
    'pypy': 'pp',
}
PYTHON_IMPLEMENTATION = platform.python_implementation()


def get_runtime_python_tag() -> str:
    """Identify the Python tag of the current runtime.

    :returns: Python tag.
    """
    python_minor_ver: tuple[int, int] = sys.version_info[:2]

    try:
        sys_impl = sys.implementation.name
    except AttributeError:
        sys_impl = PYTHON_IMPLEMENTATION.lower()

    python_tag_prefix = PYTHON_IMPLEMENTATION_MAP.get(sys_impl, sys_impl)

    python_minor_ver_tag = ''.join(map(str, python_minor_ver))

    return f'{python_tag_prefix!s}{python_minor_ver_tag!s}'


def get_constraint_file_path(  # noqa: WPS210 -- no way to drop vars
    req_dir: pathlib.Path | str,
    toxenv: str,
    python_tag: str,
) -> pathlib.Path:
    """Identify the constraints filename for the current environment.

    :param req_dir: Requirements directory.
    :param toxenv: tox testenv.
    :param python_tag: Python tag.
    :returns: Constraints filename for the current environment.
    """
    sys_platform = sys.platform
    platform_machine = platform.machine().lower()

    if toxenv in {'py', 'python'}:
        env_prefix = 'pypy' if PYTHON_IMPLEMENTATION == 'PyPy' else 'py'
        python_ver_num = python_tag[2:]
        toxenv = f'{env_prefix}{python_ver_num}'

    if sys_platform == 'linux2':
        sys_platform = 'linux'

    constraint_name = (
        f'{toxenv}-{python_tag}-{sys_platform}-{platform_machine}'
    )
    return (pathlib.Path(req_dir) / constraint_name).with_suffix('.txt')


def run_cmd(cmd: list[str] | tuple[str, ...]) -> None:
    """Invoke a shell command after logging it.

    :param cmd: The command to invoke.
    """
    escaped_cmd = shlex.join(cmd)
    print(f'Invoking the following command: {escaped_cmd!s}')  # noqa: T201, WPS421
    subprocess.check_call(cmd)  # noqa: S603
