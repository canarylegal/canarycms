"""Firm package canary-firm.json + compatibility gate."""

from __future__ import annotations

import json
from pathlib import Path

from app.firm_package import evaluate_firm_package_status, firm_package_allows_module, load_package_manifest


def test_compatible_package(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "canary-firm.json").write_text(
        json.dumps(
            {
                "version": 1,
                "package_id": "example_firm_pilot",
                "package_version": "1.0.0",
                "label": "Pilot",
                "requires_canary": ">=2.0.0 <3.0.0",
                "mounts": ["module"],
                "modules": ["example_pilot"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_PACKAGE_DIR", str(root))
    monkeypatch.setenv("CANARY_PRODUCT_VERSION", "2.0.0")
    import app.firm_package as fp

    fp._PACKAGE_CACHE = None
    fp._STATUS_CACHE = None
    m = load_package_manifest(force=True)
    assert m is not None
    assert m["package_id"] == "example_firm_pilot"
    st = evaluate_firm_package_status(force=True)
    assert st.attached and st.compatible and not st.fault
    assert firm_package_allows_module(force=False)


def test_incompatible_package_refuses_module(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "canary-firm.json").write_text(
        json.dumps(
            {
                "version": 1,
                "package_id": "example_firm_pilot",
                "package_version": "1.0.0",
                "requires_canary": ">=2.0.0 <3.0.0",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_PACKAGE_DIR", str(root))
    monkeypatch.setenv("CANARY_PRODUCT_VERSION", "3.0.0")
    import app.firm_package as fp

    fp._PACKAGE_CACHE = None
    fp._STATUS_CACHE = None
    st = evaluate_firm_package_status(force=True)
    assert st.fault and not st.compatible
    assert not firm_package_allows_module(force=False)
