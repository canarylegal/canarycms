"""Firm module manifest + default payload (Phase 3)."""

from __future__ import annotations

import json
from pathlib import Path

from app.firm_module_runtime import _default_payload, load_manifest


def test_load_manifest_from_dir(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "module"
    module.mkdir()
    (module / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "module_id": "example_pilot",
                "label": "Purchase pipeline",
                "stages": ["Instruction", "Exchange"],
                "checklist": ["ID verified"],
                "attr_fields": [{"key": "chain_position", "label": "Chain"}],
                "integration_stub": "log_only",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_MODULE_DIR", str(module))
    # Clear cache
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    rt._manifest_mtime = None
    m = load_manifest(force=True)
    assert m is not None
    assert m["module_id"] == "example_pilot"
    payload = _default_payload(m)
    assert payload["stage"] == "Instruction"
    assert payload["checklist"][0]["label"] == "ID verified"
    assert payload["attrs"]["chain_position"] == ""
    assert payload["integration"]["stub"] == "log_only"


def test_no_module_dir(monkeypatch) -> None:
    monkeypatch.delenv("FIRM_MODULE_DIR", raising=False)
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    # Point away from /firm/module if present in CI
    monkeypatch.setattr(rt, "firm_module_dir", lambda: None)
    assert load_manifest(force=True) is None
