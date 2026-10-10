#!/usr/bin/env python3
"""Fail CI when commercial vendor work lands in Core instead of canary-commercial.

Historical Core Alembic + soft shims are allowed; new vendor DDL / UI / routers are not.
See docs/COMMERCIAL_PACKAGE.md and backend/alembic/COMMERCIAL_SCHEMA.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Core revisions that already created DocuSign / Casera / HMLR / search tables.
# Do not add to this set — put new DDL in canary-commercial/module/migrations/versions/.
_ALLOWED_VENDOR_ALEMBIC = frozenset(
    {
        "c9a8b7c6d5e4_casera_integration.py",
        "hm1a2b3c4d5e_hmlr_integration.py",
        "sc1a2b3c4d5e_casera_order_selection.py",
        "sc2a2b3c4d5e_casera_finance_multifile.py",
        "sc3a2b3c4d5e_casera_email_on_result.py",
        "sp1a2b3c4d5e_search_provider_settings.py",
        "v5w6x7y8z9a0_docusign_integration.py",
        "w6x7y8z9a0b1_docusign_costs_ledger.py",
    }
)

_VENDOR_ALEMBIC_HINT = re.compile(
    r"\b(casera|hmlr|docusign|search_integration|search_provider)\b",
    re.IGNORECASE,
)

# UI that must live in the commercial IIFE, not Core.
_FORBIDDEN_FRONTEND = (
    "frontend/src/AdminCasera.tsx",
    "frontend/src/AdminHmlr.tsx",
    "frontend/src/AdminDocuSign.tsx",
    "frontend/src/AdminSearches.tsx",
    "frontend/src/AdminIntegrations.tsx",
    "frontend/src/DocusignPage.tsx",
    "frontend/src/SendDocusignModal.tsx",
    "frontend/src/CaseDetailSearchesPanel.tsx",
    "frontend/src/CaseDetailHmlrPanel.tsx",
    "frontend/src/case/CaseDetailSearchesPanel.tsx",
    "frontend/src/case/CaseDetailHmlrPanel.tsx",
)

# Connector routers belong in canary_commercial.register — not Core routers/.
_FORBIDDEN_ROUTER_GLOBS = (
    "backend/app/routers/*casera*",
    "backend/app/routers/*hmlr*",
    "backend/app/routers/*docusign*",
    "backend/app/routers/*searches*",
)

# Deleted Level-C soft shims — Core uses commercial_hooks + canary_commercial.*.
_FORBIDDEN_SHIMS = (
    "backend/app/docusign_client.py",
    "backend/app/docusign_tabs.py",
    "backend/app/docusign_signing_service.py",
    "backend/app/docusign_settings.py",
    "backend/app/casera_client.py",
    "backend/app/casera_settings.py",
    "backend/app/casera_service.py",
    "backend/app/hmlr_client.py",
    "backend/app/hmlr_service.py",
    "backend/app/hmlr_settings.py",
    "backend/app/search_settings.py",
)


def _fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)


def check_alembic(failures: list[str]) -> None:
    versions = ROOT / "backend" / "alembic" / "versions"
    if not versions.is_dir():
        _fail(f"missing {versions.relative_to(ROOT)}", failures)
        return
    for path in sorted(versions.glob("*.py")):
        if path.name in _ALLOWED_VENDOR_ALEMBIC:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _VENDOR_ALEMBIC_HINT.search(text):
            _fail(
                f"new Core Alembic vendor DDL: {path.relative_to(ROOT)} "
                f"(add SQL under canary-commercial/module/migrations/versions/ instead)",
                failures,
            )


def check_frontend(failures: list[str]) -> None:
    for rel in _FORBIDDEN_FRONTEND:
        if (ROOT / rel).is_file():
            _fail(
                f"commercial UI back in Core: {rel} "
                f"(implement in canary-commercial/module/ui and export a slot)",
                failures,
            )


def check_routers(failures: list[str]) -> None:
    routers = ROOT / "backend" / "app" / "routers"
    if not routers.is_dir():
        return
    for pattern in _FORBIDDEN_ROUTER_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file():
                _fail(
                    f"commercial router in Core: {path.relative_to(ROOT)} "
                    f"(register from canary_commercial.register instead)",
                    failures,
                )


def check_shims(failures: list[str]) -> None:
    for rel in _FORBIDDEN_SHIMS:
        if (ROOT / rel).is_file():
            _fail(
                f"legacy commercial shim reintroduced: {rel} "
                f"(use app.commercial_hooks or canary_commercial.*)",
                failures,
            )


def main() -> int:
    failures: list[str] = []
    check_alembic(failures)
    check_frontend(failures)
    check_routers(failures)
    check_shims(failures)
    if failures:
        print("commercial boundary check FAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nSee docs/COMMERCIAL_PACKAGE.md — future DocuSign/Casera/HMLR work "
            "belongs in canary-commercial.",
            file=sys.stderr,
        )
        return 1
    print("commercial boundary check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
