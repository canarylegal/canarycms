"""OWA compose deeplinks for Graph-created drafts."""

from __future__ import annotations

from app.owa_urls import (
    build_owa_compose_deeplink_from_graph_weblink,
    build_owa_compose_prefill_url,
    build_owa_open_graph_draft_compose_urls,
    owa_compose_item_id_from_graph_body,
)


def _graph_body(item_id: str, *, host: str = "outlook.cloud.microsoft") -> dict:
    return {
        "id": "GraphApiIdDifferent",
        "webLink": f"https://{host}/owa/?ItemID={item_id}&exvsurl=1&viewmodel=ReadMessageItem",
    }


def test_compose_item_id_prefers_weblink_itemid() -> None:
    body = _graph_body("RestId456")
    assert owa_compose_item_id_from_graph_body(body) == "RestId456"


def test_open_draft_uses_configured_owa_host_not_weblink_office365() -> None:
    item_id = "AAMkAGI2THVSAAA="
    path_style, query_style = build_owa_open_graph_draft_compose_urls(
        _graph_body(item_id, host="outlook.office365.com"),
        "https://outlook.cloud.microsoft/mail",
    )
    assert "outlook.cloud.microsoft" in query_style
    assert "outlook.office365.com" not in query_style
    assert "/deeplink/compose?ItemID=" in query_style
    assert "RestId456" in query_style or "RestId456" in path_style


def test_compose_deeplink_from_weblink_strips_read_viewmodel() -> None:
    item_id = "AAMkAGI2THVSAAA="
    body = _graph_body(item_id)
    url = build_owa_compose_deeplink_from_graph_weblink(
        body,
        "https://outlook.cloud.microsoft/mail",
    )
    assert "outlook.cloud.microsoft" in url
    assert "outlook.cloud.microsoft" in url
    assert "/mail/deeplink/compose?" in url
    assert "/mail/0/deeplink/compose" not in url
    assert "outlook.office.com" not in url
    assert "/deeplink/compose/AAMk" not in url.split("?")[0]
    assert "ItemID=" in url
    assert "to=" not in url
    assert "subject=" not in url
    assert "popoutv2=1" in url
    assert "subject=" not in url
    assert "to=" not in url
    assert "ReadMessage" not in url
    assert "viewmodel" not in url.lower() or "readmessage" not in url.lower()


def test_prefill_on_configured_host() -> None:
    url = build_owa_compose_prefill_url(
        "https://outlook.cloud.microsoft/mail",
        to="a@example.com",
        subject="Hi",
        body="Hello",
        graph_body=_graph_body("AAMkX"),
    )
    assert "outlook.cloud.microsoft" in url
    assert "to=a%40example.com" in url
