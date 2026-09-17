"""Guards on the version string that CI rewrites into ``copy_tool/_version.py``.

The stamp is how a user's log file identifies which build they are running, so
a silently mangled version string defeats the whole point of stamping it.
"""

import re

import pytest

from copy_tool._version import __version__

version_mod = pytest.importorskip('packaging.version')
Version = version_mod.Version


def test_version_is_valid_pep440():
    """An invalid version makes ``pip install .`` fail outright."""
    Version(__version__)


@pytest.mark.parametrize('stamp', [
    '1.3.0',                 # v* tag build
    '1.3.0+edge.g0012345',   # main push
    '1.3.0+dev.gabcdef01',   # pull request build
])
def test_ci_stamps_round_trip(stamp):
    """Every shape CI writes must survive PEP 440 normalization unchanged."""
    assert str(Version(stamp)) == stamp


def test_unprefixed_numeric_hash_is_corrupted():
    """Why CI prefixes the short hash with 'g'.

    PEP 440 treats an all-numeric local segment as a number, so a hash like
    0012345 loses its leading zeros and no longer names any commit.
    """
    assert str(Version('1.3.0+edge.0012345')) == '1.3.0+edge.12345'


def test_checked_in_version_is_a_bare_release():
    """The tracked file holds the plain release version; CI adds any suffix."""
    assert re.fullmatch(r'\d+\.\d+\.\d+', __version__)
