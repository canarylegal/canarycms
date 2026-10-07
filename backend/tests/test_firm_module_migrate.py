"""Firm SQL migration runner (Phase 5)."""

from __future__ import annotations

import json
from pathlib import Path

from app.firm_module_migrate import _list_revisions, migrations_dir


def test_list_revisions_sorted(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "module"
    versions = module / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "002_later.sql").write_text("SELECT 2;", encoding="utf-8")
    (versions / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (versions / "readme.txt").write_text("nope", encoding="utf-8")
    (module / "manifest.json").write_text(
        json.dumps({"version": 1, "module_id": "example_pilot", "storage": {"schema": "firm_example_pilot"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_MODULE_DIR", str(module))
    import app.firm_module_runtime as rt

    rt._manifest_cache = None
    rt._manifest_mtime = None
    assert migrations_dir() == versions
    revs = _list_revisions(versions)
    assert [r for r, _ in revs] == ["001", "002"]
