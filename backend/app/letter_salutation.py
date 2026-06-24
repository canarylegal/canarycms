"""Letter salutation options and merge resolution for case contacts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.matter_contact_constants import CLIENT_SLUG, normalize_matter_contact_type_slug


class LetterSalutation(str, Enum):
    dear_first_name_informal = "dear_first_name_informal"
    dear_first_name_formal = "dear_first_name_formal"
    dear_sir_madam = "dear_sir_madam"
    dear_sir_or_madam = "dear_sir_or_madam"
    dear_sirs = "dear_sirs"
    dear_firm_name = "dear_firm_name"
    custom = "custom"


_FAITHFULLY_SALUTATIONS: frozenset[str] = frozenset(
    {
        LetterSalutation.dear_sir_madam.value,
        LetterSalutation.dear_sir_or_madam.value,
        LetterSalutation.dear_sirs.value,
    }
)


def _s_str(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contact_type_str(contact: Any | None) -> str:
    if not contact:
        return ""
    t = getattr(contact, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        return str(t.value)
    return str(t)


def _is_client_matter_type(matter_contact_type: str | None) -> bool:
    return normalize_matter_contact_type_slug(matter_contact_type) == CLIENT_SLUG


def default_letter_salutation(*, matter_contact_type: str | None, contact_type: str) -> str:
    if contact_type == "organisation":
        return LetterSalutation.dear_sir_madam.value
    if _is_client_matter_type(matter_contact_type):
        return LetterSalutation.dear_first_name_informal.value
    return LetterSalutation.dear_sir_madam.value


def allowed_letter_salutations(*, matter_contact_type: str | None, contact_type: str) -> frozenset[str]:
    if contact_type == "organisation":
        return frozenset(
            {
                LetterSalutation.dear_sir_madam.value,
                LetterSalutation.dear_sirs.value,
                LetterSalutation.dear_firm_name.value,
                LetterSalutation.custom.value,
            }
        )
    if _is_client_matter_type(matter_contact_type):
        return frozenset(
            {
                LetterSalutation.dear_first_name_informal.value,
                LetterSalutation.dear_first_name_formal.value,
                LetterSalutation.custom.value,
            }
        )
    return frozenset(
        {
            LetterSalutation.dear_sir_madam.value,
            LetterSalutation.dear_sir_or_madam.value,
            LetterSalutation.custom.value,
        }
    )


def coerce_letter_salutation(
    value: str | None,
    *,
    matter_contact_type: str | None,
    contact_type: str,
) -> str:
    raw = (value or "").strip()
    allowed = allowed_letter_salutations(
        matter_contact_type=matter_contact_type,
        contact_type=contact_type,
    )
    if raw in allowed:
        return raw
    return default_letter_salutation(
        matter_contact_type=matter_contact_type,
        contact_type=contact_type,
    )


def effective_letter_salutation(contact: Any | None) -> str:
    if not contact:
        return LetterSalutation.dear_sir_madam.value
    stored = _s_str(getattr(contact, "letter_salutation", None))
    return coerce_letter_salutation(
        stored or None,
        matter_contact_type=getattr(contact, "matter_contact_type", None),
        contact_type=_contact_type_str(contact),
    )


def informal_first_name(contact: Any | None) -> str:
    if not contact:
        return ""
    first = _s_str(getattr(contact, "first_name", None))
    if first:
        return first
    display = _s_str(getattr(contact, "name", None))
    if not display:
        return ""
    parts = display.split()
    return parts[0] if parts else ""


def join_informal_first_names(contacts: list[Any]) -> str:
    names = [n for c in contacts if (n := informal_first_name(c))]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def formal_addressee_name(contact: Any | None) -> str:
    if not contact:
        return ""
    title = _s_str(getattr(contact, "title", None))
    last = _s_str(getattr(contact, "last_name", None))
    if title and last:
        return f"{title} {last}"
    if last:
        return last
    return _s_str(getattr(contact, "name", None))


def firm_display_name(contact: Any | None) -> str:
    if not contact:
        return ""
    trading = _s_str(getattr(contact, "trading_name", None))
    if trading:
        return trading
    return _s_str(getattr(contact, "company_name", None)) or _s_str(getattr(contact, "name", None))


def _format_custom_salutation(custom: str | None) -> str:
    text = _s_str(custom)
    if not text:
        return ""
    if text.lower().startswith("dear"):
        body = text.rstrip()
        if not body.endswith(","):
            body = f"{body},"
        return body
    body = text.rstrip(",").strip()
    return f"Dear {body}," if body else ""


def letter_salutation_body(
    contact: Any | None,
    *,
    informal_name_contacts: list[Any] | None = None,
) -> str:
    """Text after ``Dear `` and before the trailing comma (no ``Dear`` prefix)."""

    if not contact:
        return ""
    style = effective_letter_salutation(contact)
    if style == LetterSalutation.custom.value:
        custom = _s_str(getattr(contact, "letter_salutation_custom", None))
        full = _format_custom_salutation(custom)
        if full.lower().startswith("dear "):
            body = full[5:].lstrip()
            return body[:-1].strip() if body.endswith(",") else body.strip()
        return custom.rstrip(",").strip()

    if style == LetterSalutation.dear_first_name_informal.value:
        if informal_name_contacts and len(informal_name_contacts) > 1:
            return join_informal_first_names(informal_name_contacts)
        return informal_first_name(contact)

    if style == LetterSalutation.dear_first_name_formal.value:
        return formal_addressee_name(contact)

    if style == LetterSalutation.dear_sir_madam.value:
        return "Sir / Madam"

    if style == LetterSalutation.dear_sir_or_madam.value:
        return "Sir or Madam"

    if style == LetterSalutation.dear_sirs.value:
        return "Sirs"

    if style == LetterSalutation.dear_firm_name.value:
        return firm_display_name(contact)

    return _s_str(getattr(contact, "name", None))


def resolve_letter_dear_line(
    contact: Any | None,
    *,
    informal_name_contacts: list[Any] | None = None,
) -> str:
    body = letter_salutation_body(contact, informal_name_contacts=informal_name_contacts)
    return f"Dear {body}," if body else ""


def primary_client_letter_dear_line(clients: list[Any]) -> str:
    if not clients:
        return ""
    first = clients[0]
    style = effective_letter_salutation(first)
    if style == LetterSalutation.dear_first_name_informal.value and len(clients) > 1:
        return resolve_letter_dear_line(first, informal_name_contacts=clients)
    return resolve_letter_dear_line(first)


def resolve_letter_sign_off(contact: Any | None) -> str:
    """British English closing line from the contact's letter salutation setting."""

    if not contact:
        return "Yours faithfully,"
    style = effective_letter_salutation(contact)
    if style in _FAITHFULLY_SALUTATIONS:
        return "Yours faithfully,"
    return "Yours sincerely,"


def primary_client_letter_sign_off(clients: list[Any]) -> str:
    if not clients:
        return "Yours faithfully,"
    return resolve_letter_sign_off(clients[0])
