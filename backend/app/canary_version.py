"""Canary product version (semver) for firm-package compatibility checks."""

from __future__ import annotations

import os
import re

# Default aligns with CMS 2.0 line (frontend package.json / release tags).
_DEFAULT = "2.0.0"
_VER_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<pre>[-+][0-9A-Za-z.-]+)?$"
)


def canary_product_version() -> str:
    """Running Canary product version string (no leading ``v``).

    Set ``CANARY_PRODUCT_VERSION`` at image build / deploy (e.g. ``2.0.0``).
    """
    raw = (os.getenv("CANARY_PRODUCT_VERSION") or "").strip()
    if not raw:
        return _DEFAULT
    return raw[1:] if raw.startswith("v") or raw.startswith("V") else raw


def parse_version(version: str) -> tuple[int, int, int]:
    m = _VER_RE.match((version or "").strip())
    if not m:
        raise ValueError(f"Invalid semver: {version!r}")
    return int(m.group("major")), int(m.group("minor")), int(m.group("patch"))


def _cmp(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a > b) - (a < b)


def version_satisfies(version: str, spec: str) -> bool:
    """Return True if ``version`` satisfies a simple range like ``>=2.0.0 <3.0.0``.

    Supports space-separated clauses with operators ``>=``, ``>``, ``<=``, ``<``, ``==``, ``=``.
    """
    ver = parse_version(version)
    clauses = [c for c in (spec or "").replace(",", " ").split() if c.strip()]
    if not clauses:
        return True
    op_re = re.compile(r"^(>=|<=|>|<|==|=)(.+)$")
    for clause in clauses:
        m = op_re.match(clause.strip())
        if not m:
            raise ValueError(f"Invalid version clause: {clause!r}")
        op, rhs = m.group(1), m.group(2)
        other = parse_version(rhs)
        c = _cmp(ver, other)
        if op in ("=", "==") and c != 0:
            return False
        if op == ">=" and c < 0:
            return False
        if op == ">" and c <= 0:
            return False
        if op == "<=" and c > 0:
            return False
        if op == "<" and c >= 0:
            return False
    return True
