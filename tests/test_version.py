"""Guards on the version string that CI rewrites into ``copy_tool/_version.py``.

The stamp is how a user's log file identifies which build they are running, so
a silently mangled version string defeats the whole point of stamping it.
"""

import pytest

from copy_tool._version import __version__

version_mod = pytest.importorskip('packaging.version')
Version = version_mod.Version


def test_version_is_valid_pep440():
    """An invalid version makes ``pip install .`` fail outright."""
    Version(__version__)


@pytest.mark.parametrize('stamp', [
    '1.3.0',                      # v* tag build
    '1.3.0+edge.g0012345',        # main push
    '1.3.0+dev.gabcdef01',        # pull request build
    '1.4.0.dev0',                 # between releases
    '1.4.0.dev0+edge.g0012345',   # main push while a dev version is tracked
    '1.4.0rc1+dev.gabcdef01',     # pull request against a release candidate
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


def test_checked_in_version_is_canonical():
    """The tracked version is what CI appends its stamp to.

    A non-canonical spelling like 1.4.0dev0 normalizes on install, so the
    built distribution would carry a version the file never names.
    """
    assert str(Version(__version__)) == __version__


def test_checked_in_version_has_no_local_segment():
    """The local segment is CI's to add; two of them is not a valid version."""
    assert Version(__version__).local is None
