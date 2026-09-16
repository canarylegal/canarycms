"""Small shared text helpers for docx merge utilities."""
from __future__ import annotations

def _s_str(v: object) -> str:
    return (v or "").strip() if isinstance(v, str) else ""


def _initial_letter(v: object) -> str:
    t = _s_str(v)
    return t[0].upper() if t else ""
