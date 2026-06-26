"""Reserved precedent ``reference`` values interpreted by the server."""

from __future__ import annotations

# Letter compose with “Blank (no precedent)” resolves to this precedent row (global scope, kind=letter).
BLANK_LETTER_PRECEDENT_REFERENCE = "BLANK_LETTER"

# Approved invoice .docx layout (global scope, kind=document).
INVOICE_TEMPLATE_PRECEDENT_REFERENCE = "INVOICE_TEMPLATE"

# Case completion statement .docx layout (global scope, kind=document).
COMPLETION_STATEMENT_PRECEDENT_REFERENCE = "COMPLETION_STATEMENT"

# Fee-scale quote .docx layout (global scope, kind=document).
QUOTE_TEMPLATE_PRECEDENT_REFERENCE = "QUOTE_TEMPLATE"

# E-mail compose with “Blank (no precedent)” resolves to this precedent row (global scope, kind=email).
BLANK_EMAIL_PRECEDENT_REFERENCE = "BLANK_EMAIL"

# E-mail body template for sending a quote with attachment (global scope, kind=email).
QUOTE_EMAIL_PRECEDENT_REFERENCE = "QUOTE_EMAIL"

RESERVED_PRECEDENT_REFERENCES: frozenset[str] = frozenset(
    {
        BLANK_LETTER_PRECEDENT_REFERENCE,
        BLANK_EMAIL_PRECEDENT_REFERENCE,
        INVOICE_TEMPLATE_PRECEDENT_REFERENCE,
        COMPLETION_STATEMENT_PRECEDENT_REFERENCE,
        QUOTE_TEMPLATE_PRECEDENT_REFERENCE,
        QUOTE_EMAIL_PRECEDENT_REFERENCE,
    }
)

# Global document templates with dedicated compose / generation merge handling.
SYSTEM_DOCUMENT_TEMPLATE_REFERENCES: frozenset[str] = frozenset(
    {
        INVOICE_TEMPLATE_PRECEDENT_REFERENCE,
        COMPLETION_STATEMENT_PRECEDENT_REFERENCE,
        QUOTE_TEMPLATE_PRECEDENT_REFERENCE,
    }
)


def is_reserved_precedent_reference(ref: str) -> bool:
    return (ref or "").strip().casefold() in {r.casefold() for r in RESERVED_PRECEDENT_REFERENCES}
