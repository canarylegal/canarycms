"""Brand / vendor configuration (Phase 2)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import brand_config as bc


def test_defaults_are_canary_product(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CANARY_BRAND_PRODUCT_NAME",
        "CANARY_BRAND_VENDOR_URL",
        "CANARY_BRAND_POWERED_BY_LABEL",
        "CANARY_BRAND_POWERED_BY_URL",
        "CANARY_BRAND_POWERED_BY_HIDE",
        "CANARY_BRAND_SUPPORT_INBOX",
        "CANARY_SUPPORT_INBOX",
        "CANARY_BRAND_TOTP_ISSUER",
        "TOTP_ISSUER",
        "CANARY_BRAND_WEBAUTHN_RP_NAME",
        "WEBAUTHN_RP_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    assert bc.product_name() == "Canary"
    assert "canarylegalsoftware.co.uk" in bc.vendor_url()
    assert "Canary Legal Software" in bc.env_powered_by_label()
    assert bc.env_powered_by_hide() is False
    assert bc.env_support_inbox() == "colin@canarylegalsoftware.co.uk"
    assert bc.totp_issuer() == "Canary"
    assert bc.webauthn_rp_name() == "Canary"


def test_env_aliases_and_admin_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BRAND_PRODUCT_NAME", "Hawthorn CMS")
    monkeypatch.setenv("TOTP_ISSUER", "LegacyIssuer")
    monkeypatch.setenv("CANARY_BRAND_SUPPORT_INBOX", "ops@hawthorn.example")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_HIDE", "0")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_LABEL", "Powered by Hawthorn")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_URL", "https://hawthorn.example")

    assert bc.product_name() == "Hawthorn CMS"
    assert bc.totp_issuer() == "LegacyIssuer"
    assert bc.env_support_inbox() == "ops@hawthorn.example"

    firm = SimpleNamespace(
        brand_support_inbox="desk@firm.example",
        brand_powered_by_label="Powered by Acme",
        brand_powered_by_url="https://acme.example",
        brand_powered_by_hide=True,
    )
    assert bc.resolve_support_inbox(firm) == "desk@firm.example"
    pb = bc.resolve_powered_by(firm)
    assert pb.hide is True
    assert pb.label == "Powered by Acme"
    assert pb.url == "https://acme.example"


def test_proprietary_profile_has_no_canary_legal_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BRAND_PRODUCT_NAME", "Example Firm Platform")
    monkeypatch.setenv("CANARY_BRAND_VENDOR_URL", "https://platform.example")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_LABEL", "Powered by Example Firm Platform")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_URL", "https://platform.example")
    monkeypatch.setenv("CANARY_BRAND_POWERED_BY_HIDE", "1")
    monkeypatch.setenv("CANARY_BRAND_SUPPORT_INBOX", "support@platform.example")
    monkeypatch.setenv("CANARY_BRAND_TOTP_ISSUER", "Example Firm Platform")
    monkeypatch.setenv("CANARY_BRAND_WEBAUTHN_RP_NAME", "Example Firm Platform")
    monkeypatch.setenv("CANARY_BRAND_TB_UPDATE_BASE_URL", "https://platform.example/thunderbird")
    monkeypatch.delenv("TOTP_ISSUER", raising=False)
    monkeypatch.delenv("WEBAUTHN_RP_NAME", raising=False)
    monkeypatch.delenv("CANARY_SUPPORT_INBOX", raising=False)

    hits = bc.proprietary_leak_hits()
    assert hits == [], hits
    assert bc.env_powered_by_hide() is True
