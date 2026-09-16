"""ONLYOFFICE Document Server SSRF base URL normalization."""

from __future__ import annotations

import pytest

from app.onlyoffice_ssrf_url import default_internal_base_for_ds, normalize_onlyoffice_ssrf_base


@pytest.fixture(autouse=True)
def _clear_ssrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ONLYOFFICE_ALLOW_LAN_INTERNAL", raising=False)
    monkeypatch.delenv("ONLYOFFICE_APP_URL_INTERNAL", raising=False)
    monkeypatch.delenv("ONLYOFFICE_PREFER_IPV4_FOR_DS", raising=False)
    monkeypatch.delenv("ONLYOFFICE_DOCKER_PEER_SERVICE", raising=False)
    monkeypatch.delenv("ONLYOFFICE_DOCKER_PEER_PORT", raising=False)


def test_normalize_rewrites_private_rfc1918_ip() -> None:
    assert normalize_onlyoffice_ssrf_base("http://192.168.1.50:8000") == "http://backend:8000"


def test_normalize_rewrites_10_dot_private_ip() -> None:
    assert normalize_onlyoffice_ssrf_base("http://10.0.0.9:8000/") == "http://backend:8000"


def test_normalize_rewrites_loopback_ip() -> None:
    assert normalize_onlyoffice_ssrf_base("http://127.0.0.1:8000") == "http://backend:8000"


def test_normalize_rewrites_localhost_hostname() -> None:
    assert normalize_onlyoffice_ssrf_base("http://localhost:8000") == "http://backend:8000"


def test_normalize_rewrites_link_local_ip() -> None:
    assert normalize_onlyoffice_ssrf_base("http://169.254.1.2:8000") == "http://backend:8000"


def test_normalize_rewrites_cgnat_tailscale_range() -> None:
    assert normalize_onlyoffice_ssrf_base("http://100.64.12.34:8000") == "http://backend:8000"


def test_normalize_allow_lan_preserves_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_ALLOW_LAN_INTERNAL", "1")
    assert normalize_onlyoffice_ssrf_base("http://192.168.1.50:8000") == "http://192.168.1.50:8000"


def test_normalize_allow_lan_true_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_ALLOW_LAN_INTERNAL", "true")
    assert normalize_onlyoffice_ssrf_base("http://10.1.2.3:8000") == "http://10.1.2.3:8000"


@pytest.mark.parametrize(
    "url",
    [
        "http://backend:8000",
        "http://frontend:3000",
        "http://onlyoffice",
        "http://db:5432",
        "http://canary-backend:8000",
        "http://canary-onlyoffice",
        "http://host.docker.internal:8000",
    ],
)
def test_normalize_preserves_compose_hostnames(url: str) -> None:
    assert normalize_onlyoffice_ssrf_base(url) == url.rstrip("/")


def test_normalize_preserves_public_hostname() -> None:
    assert normalize_onlyoffice_ssrf_base("https://cms.example.com") == "https://cms.example.com"


def test_normalize_empty_returns_docker_default() -> None:
    assert normalize_onlyoffice_ssrf_base("") == "http://backend:8000"
    assert normalize_onlyoffice_ssrf_base("   ") == "http://backend:8000"


def test_default_internal_base_uses_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_APP_URL_INTERNAL", "http://backend:8000/")
    assert default_internal_base_for_ds() == "http://backend:8000"


def test_default_internal_base_rewrites_explicit_lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_APP_URL_INTERNAL", "http://192.168.0.10:8000")
    assert default_internal_base_for_ds() == "http://backend:8000"


def test_default_internal_base_without_env() -> None:
    assert default_internal_base_for_ds() == "http://backend:8000"
