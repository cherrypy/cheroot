#! /usr/bin/env python
"""A script that prints platform-specific constraints file name base."""

from __future__ import annotations

import sys

from pip_constraint_helpers import (
    get_constraint_file_path,
    get_runtime_python_tag,
)


def compute_constraint_base_name(toxenv: str) -> str:
    """Get the lock file name stem.

    :param toxenv: Name of the tox env.
    :returns: A platform-specific lock file base name for tox env.
    """
    return get_constraint_file_path(
        req_dir='',
        toxenv=toxenv,
        python_tag=get_runtime_python_tag(),
    ).stem


if __name__ == '__main__':
    print(compute_constraint_base_name(sys.argv[1]))  # noqa: T201, WPS421
