"""Semver helpers for firm-package requires_canary."""

from __future__ import annotations

import pytest

from app.canary_version import parse_version, version_satisfies


def test_parse_version() -> None:
    assert parse_version("2.0.0") == (2, 0, 0)
    assert parse_version("v2.1.3") == (2, 1, 3)


def test_range_inclusive_major() -> None:
    assert version_satisfies("2.0.0", ">=2.0.0 <3.0.0")
    assert version_satisfies("2.9.9", ">=2.0.0 <3.0.0")
    assert not version_satisfies("3.0.0", ">=2.0.0 <3.0.0")
    assert not version_satisfies("1.9.9", ">=2.0.0 <3.0.0")


def test_invalid_spec() -> None:
    with pytest.raises(ValueError):
        version_satisfies("2.0.0", "banana")
