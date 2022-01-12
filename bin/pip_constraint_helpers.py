"""A set of functions helping generating pip constraint files."""
from __future__ import print_function  # noqa: WPS422

import functools
import os
import platform
import subprocess  # noqa: S404
import sys

print_info = functools.partial(print, file=sys.stderr)


def get_runtime_python_tag():
    """Identify the Python tag of the current runtime.

    :returns: Python tag.
    """
    python_minor_ver = sys.version_info[:2]
    python_implementation = platform.python_implementation()

    if python_implementation == 'PyPy':
        python_tag_prefix = 'py'
    else:
        python_tag_prefix = 'cp'

    # pylint: disable=possibly-unused-variable
    python_minor_ver_tag = ''.join(map(str, python_minor_ver))

    python_tag = (
        '{python_tag_prefix!s}{python_minor_ver_tag!s}'.
        format(**locals())  # noqa: WPS421
    )

    if python_tag_prefix == 'cp' and python_implementation == 'CPython':
        print_info(
            'WARNING: The chosen Python interpreter tag "{python_tag}" '
            'may not match the current '
            'Python implementation "{python_implementation}"'.
            format(**locals()),  # noqa: WPS421
        )

    return python_tag


def get_constraint_file_path(req_dir, toxenv, python_tag):
    """Identify the constraints filename for the current environment.

    :param req_dir: Requirements directory.
    :param toxenv: tox testenv.
    :param python_tag: Python tag.

    :returns: Constraints filename for the current environment.
    """
    sys_platform = sys.platform
    # pylint: disable=possibly-unused-variable
    platform_machine = platform.machine().lower()

    if toxenv in {'py', 'python'}:
        toxenv = 'py{ver}'.format(ver=python_tag[2:])

    if sys_platform == 'linux2':
        sys_platform = 'linux'

    constraint_name = (
        'tox-{toxenv}-{python_tag}-{sys_platform}-{platform_machine}'.
        format(**locals())  # noqa: WPS421
    )
    return os.path.join(req_dir, os.path.extsep.join((constraint_name, 'txt')))


def make_pip_cmd(pip_args, constraint_file_path):
    """Inject a lockfile constraint into the pip command if present.

    :param pip_args: pip arguments.
    :param constraint_file_path: Path to a ``constraints.txt``-compatible file.

    :returns: pip command.
    """
    pip_cmd = [sys.executable, '-m', 'pip'] + pip_args
    if os.path.isfile(constraint_file_path):
        pip_cmd += ['--constraint', constraint_file_path]
    else:
        print_info(
            'WARNING: The expected pinned constraints file for the current env'
            'does not exist (should be "{constraint_file_path}").'.
            format(**locals()),  # noqa: WPS421
        )
    return pip_cmd


def run_cmd(cmd):
    """Invoke a shell command after logging it.

    :param cmd: The command to invoke.
    """
    print_info(
        'Invoking the following command: {cmd}'.
        format(cmd=' '.join(cmd)),
    )
    subprocess.check_call(cmd)  # noqa: S603
