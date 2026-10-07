"""Firm module manifest, slots, UI resolve, lifecycle helpers (Phase 4/5)."""

from __future__ import annotations

import json
from pathlib import Path

from app.firm_module_runtime import (
    LIFECYCLE_DOCUMENT_UPLOADED,
    LIFECYCLE_MATTER_CREATED,
    LIFECYCLE_MATTER_STATUS_CHANGED,
    _default_payload,
    load_manifest,
    resolve_ui_asset,
    slots_enabled,
    storage_schema,
)


def _write_module(tmp_path: Path, *, with_ui: bool = True) -> Path:
    module = tmp_path / "module"
    module.mkdir()
    manifest: dict = {
        "version": 1,
        "module_id": "example_pilot",
        "label": "Purchase pipeline",
        "stages": ["Instruction", "Exchange"],
        "checklist": ["ID verified"],
        "attr_fields": [{"key": "chain_position", "label": "Chain"}],
        "integration_stub": "log_only",
    }
    manifest["storage"] = {"schema": "firm_example_pilot", "case_state_table": "case_state"}
    if with_ui:
        ui_dist = module / "ui" / "dist"
        ui_dist.mkdir(parents=True)
        (ui_dist / "firm-module.js").write_text("// stub", encoding="utf-8")
        manifest["ui"] = {
            "bundle": "ui/dist/firm-module.js",
            "exports": {"matter_panel": "MatterPanel", "dashboard_widget": "DashboardWidget"},
        }
        manifest["slots"] = {
            "matter_panel": True,
            "dashboard_widget": True,
            "matter_actions": False,
            "portal_section": False,
            "admin_page": False,
        }
    (module / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return module


def test_load_manifest_from_dir(tmp_path: Path, monkeypatch) -> None:
    module = _write_module(tmp_path)
    monkeypatch.setenv("FIRM_MODULE_DIR", str(module))
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
    assert payload["pipeline_active"] is True
    assert storage_schema(m) == "firm_example_pilot"
    slots = slots_enabled(m)
    assert slots["matter_panel"] is True
    assert slots["dashboard_widget"] is True
    assert slots["matter_actions"] is False
    assert resolve_ui_asset("firm-module.js") is not None
    assert resolve_ui_asset("../secret") is None


def test_resolve_ui_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    module = _write_module(tmp_path)
    monkeypatch.setenv("FIRM_MODULE_DIR", str(module))
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    rt._manifest_mtime = None
    load_manifest(force=True)
    assert resolve_ui_asset("../../etc/passwd") is None


def test_legacy_manifest_infers_panel_slots(tmp_path: Path, monkeypatch) -> None:
    module = _write_module(tmp_path, with_ui=False)
    monkeypatch.setenv("FIRM_MODULE_DIR", str(module))
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    rt._manifest_mtime = None
    m = load_manifest(force=True)
    assert m is not None
    slots = slots_enabled(m)
    assert slots["matter_panel"] is True
    assert slots["dashboard_widget"] is True


def test_lifecycle_event_constants() -> None:
    assert LIFECYCLE_MATTER_CREATED == "lifecycle.matter.created"
    assert LIFECYCLE_DOCUMENT_UPLOADED == "lifecycle.document.uploaded"
    assert LIFECYCLE_MATTER_STATUS_CHANGED == "lifecycle.matter.status_changed"


def test_no_module_dir(monkeypatch) -> None:
    monkeypatch.delenv("FIRM_MODULE_DIR", raising=False)
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    monkeypatch.setattr(rt, "firm_module_dir", lambda: None)
    assert load_manifest(force=True) is None
