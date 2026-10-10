"""Casera placeholder PDF, status labels, and risk badge normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pikepdf
import pytest

from app.commercial_runtime import ensure_commercial_path

if not ensure_commercial_path():
    pytest.skip("requires Canary commercial package", allow_module_level=True)

from app.casera_service import build_placeholder_pdf, normalize_risk_badges, status_label


def test_build_placeholder_pdf_is_readable() -> None:
    raw = build_placeholder_pdf(
        product_name="Local Authority Search",
        ordered_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        due_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    assert raw.startswith(b"%PDF")
    assert len(raw) > 200
    with pikepdf.open(BytesIO(raw)) as pdf:
        assert len(pdf.pages) == 1


def test_status_label_complete_and_fail() -> None:
    due = datetime(2026, 3, 10, tzinfo=timezone.utc)
    assert status_label(state="Completed", due_at=due) == "Complete"
    assert status_label(state="Holding", due_at=due) == "ETA 10/03/26"
    assert "Cancel" in status_label(state="Cancelled", due_at=due)


def test_normalize_risk_badges_bool_map() -> None:
    badges = normalize_risk_badges({"flood": True, "mining": False, "radon": {"riskAvailable": True, "productIds": ["p1"]}})
    keys = {b.key for b in badges}
    assert "flood" in keys
    assert "mining" not in keys
    radon = next(b for b in badges if b.key == "radon")
    assert radon.label == "Radon"
    assert radon.product_ids == ["p1"]
