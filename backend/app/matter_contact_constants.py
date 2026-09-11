"""Slugs for matter-level contact types (stored on ``case_contact.matter_contact_type``)."""

from __future__ import annotations

CLIENT_SLUG = "client"
LAWYERS_SLUG = "lawyers"

SYSTEM_MATTER_CONTACT_SLUGS: frozenset[str] = frozenset(
    {"client", "lawyers", "new-lender", "existing-lender"}
)


def normalize_matter_contact_type_slug(raw: str | None) -> str:
    return (raw or "").strip().lower()


def is_client_matter_contact_type(raw: str | None) -> bool:
    return normalize_matter_contact_type_slug(raw) == CLIENT_SLUG


def is_exchange_matter_contact_type(raw: str | None) -> bool:
    """Non-client matter roles use matter-scoped portal exchange access."""
    slug = normalize_matter_contact_type_slug(raw)
    return bool(slug) and slug != CLIENT_SLUG
