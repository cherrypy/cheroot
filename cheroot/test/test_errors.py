"""Test suite for ``cheroot.errors``."""

import pytest

from cheroot import errors


@pytest.mark.parametrize(
    'err_names,err_nums',
    (
        (('', 'some-nonsense-name'), []),
        (
            ('EPROTOTYPE', 'EAGAIN', 'EWOULDBLOCK',
             'WSAEWOULDBLOCK', 'EPIPE'),
            [91, 11, 32]
        ),
    ),
)
def test_plat_specific_errors(err_names, err_nums):
    """Test that plat_specific_errors retrieves correct err num list."""
    actual_err_nums = errors.plat_specific_errors(*err_names)
    assert len(actual_err_nums) == len(err_nums)
    assert sorted(actual_err_nums) == sorted(err_nums)
