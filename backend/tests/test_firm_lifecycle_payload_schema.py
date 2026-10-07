"""Static Phase 7 lifecycle payload schema contract (no Docker / firm mount)."""

from __future__ import annotations

from app.firm_module_runtime import (
    LIFECYCLE_DOCUMENT_UPLOADED,
    LIFECYCLE_MATTER_CREATED,
    LIFECYCLE_MATTER_STATUS_CHANGED,
)

# Keep in sync with FIRM_MODULE_CONTRACT.md + scripts/smoke_firm_contract.py
REQUIRED: dict[str, frozenset[str]] = {
    LIFECYCLE_MATTER_CREATED: frozenset(
        {"schema_version", "case_id", "case_number", "matter_sub_type_id", "actor_user_id", "at"}
    ),
    LIFECYCLE_DOCUMENT_UPLOADED: frozenset(
        {"schema_version", "case_id", "file_id", "filename", "actor_user_id", "at"}
    ),
    LIFECYCLE_MATTER_STATUS_CHANGED: frozenset(
        {"schema_version", "case_id", "case_number", "status", "actor_user_id", "at"}
    ),
}


def test_lifecycle_event_type_strings() -> None:
    assert LIFECYCLE_MATTER_CREATED == "lifecycle.matter.created"
    assert LIFECYCLE_DOCUMENT_UPLOADED == "lifecycle.document.uploaded"
    assert LIFECYCLE_MATTER_STATUS_CHANGED == "lifecycle.matter.status_changed"


def test_published_payload_key_sets() -> None:
    for event_type, keys in REQUIRED.items():
        assert "schema_version" in keys
        assert "case_id" in keys
        assert "at" in keys
        assert "actor_user_id" in keys


def test_example_payloads_satisfy_contract() -> None:
    samples = {
        LIFECYCLE_MATTER_CREATED: {
            "schema_version": 1,
            "case_id": "00000000-0000-0000-0000-000000000001",
            "case_number": "000001",
            "matter_sub_type_id": "00000000-0000-0000-0000-000000000002",
            "actor_user_id": "00000000-0000-0000-0000-000000000003",
            "at": "2026-10-07T12:00:00+00:00",
        },
        LIFECYCLE_DOCUMENT_UPLOADED: {
            "schema_version": 1,
            "case_id": "00000000-0000-0000-0000-000000000001",
            "file_id": "00000000-0000-0000-0000-000000000004",
            "filename": "x.pdf",
            "actor_user_id": None,
            "at": "2026-10-07T12:00:00+00:00",
        },
        LIFECYCLE_MATTER_STATUS_CHANGED: {
            "schema_version": 1,
            "case_id": "00000000-0000-0000-0000-000000000001",
            "case_number": "000001",
            "status": "closed",
            "actor_user_id": None,
            "at": "2026-10-07T12:00:00+00:00",
        },
    }
    for event_type, payload in samples.items():
        missing = REQUIRED[event_type] - set(payload.keys())
        assert not missing, f"{event_type}: missing {missing}"
        assert payload["schema_version"] == 1
