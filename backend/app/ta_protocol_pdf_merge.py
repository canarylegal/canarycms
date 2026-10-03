"""Map Canary merge fields onto Law Society TA6 / TA7 / TA10 PDF AcroForm fields.

These precedents are fillable PDFs (not DOCX). Compose copies the PDF and prefills
identity / solicitor header fields from case data; remaining questions stay editable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.canary_sign_pdf import fill_acroform

log = logging.getLogger(__name__)

# Outward + inward UK postcode (allows optional space).
_UK_POSTCODE_RE = re.compile(
    r"^(GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})$",
    re.IGNORECASE,
)

TA_PROTOCOL_REFERENCES = frozenset({"TA6", "TA7", "TA10"})


def _s(value: Any) -> str:
    return str(value or "").strip()


def join_seller_names(names: list[str]) -> str:
    """Join seller/client display names for Law Society “full name of the sellers” boxes."""
    parts = [n.strip() for n in names if n and n.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def split_address_and_postcode(address_block: str, address_one_line: str = "") -> tuple[str, str]:
    """Return (address without postcode, postcode) from property merge fields."""
    block = _s(address_block)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    postcode = ""
    if lines and _UK_POSTCODE_RE.match(lines[-1].replace("  ", " ")):
        postcode = lines[-1].upper()
        # Normalise single space before inward code when missing.
        postcode = re.sub(r"\s+", " ", postcode).strip()
        if " " not in postcode and len(postcode) >= 5:
            postcode = f"{postcode[:-3]} {postcode[-3:]}"
        lines = lines[:-1]
    address = "\n".join(lines) if lines else _s(address_one_line)
    if not postcode and address_one_line:
        # Last comma-separated token may be the postcode.
        bits = [b.strip() for b in address_one_line.split(",") if b.strip()]
        if bits and _UK_POSTCODE_RE.match(bits[-1].replace("  ", " ")):
            postcode = bits[-1].upper()
            postcode = re.sub(r"\s+", " ", postcode).strip()
            if " " not in postcode and len(postcode) >= 5:
                postcode = f"{postcode[:-3]} {postcode[-3:]}"
            if not lines:
                address = ", ".join(bits[:-1])
    return address, postcode


def firm_address_without_postcode(firm_address_block: str, firm_postcode: str) -> str:
    block = _s(firm_address_block)
    pc = _s(firm_postcode)
    if not block:
        return ""
    if not pc:
        return block
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    pc_norm = re.sub(r"\s+", "", pc).upper()
    kept = [ln for ln in lines if re.sub(r"\s+", "", ln).upper() != pc_norm]
    return "\n".join(kept)


def seller_names_from_merge_fields(fields: dict[str, str]) -> str:
    """Prefer explicit primary + CLIENT slots built for merge-all; fall back to PRIMARY_CLIENT_NAME."""
    names: list[str] = []
    primary = _s(fields.get("[PRIMARY_CLIENT_NAME]"))
    # Unsuffixed company/person from client 1
    c1_company = _s(fields.get("[COMPANY_NAME]"))
    c1_trading = _s(fields.get("[TRADING_NAME]"))
    c1_person = " ".join(
        p
        for p in (
            _s(fields.get("[TITLE]")),
            _s(fields.get("[FIRST_NAME]")),
            _s(fields.get("[MIDDLE_NAME]")),
            _s(fields.get("[LAST_NAME]")),
        )
        if p
    ).strip()
    first = primary or c1_company or c1_trading or c1_person
    if first:
        names.append(first)
    for slot in (2, 3, 4):
        company = _s(fields.get(f"[COMPANY_NAME_{slot}]"))
        trading = _s(fields.get(f"[TRADING_NAME_{slot}]"))
        person = " ".join(
            p
            for p in (
                _s(fields.get(f"[TITLE_{slot}]")),
                _s(fields.get(f"[FIRST_NAME_{slot}]")),
                _s(fields.get(f"[MIDDLE_NAME_{slot}]")),
                _s(fields.get(f"[LAST_NAME_{slot}]")),
            )
            if p
        ).strip()
        label = company or trading or person
        if label:
            names.append(label)
    return join_seller_names(names)


def acroform_values_for_ta_reference(
    reference: str,
    fields: dict[str, str],
    *,
    fee_earner_email: str = "",
) -> dict[str, Any]:
    """Build AcroForm name→value map for a TA protocol PDF precedent reference."""
    ref = (reference or "").strip().upper()
    sellers = seller_names_from_merge_fields(fields)
    prop_block = _s(fields.get("[PROPERTY_ADDRESS_BLOCK]"))
    prop_one = _s(fields.get("[PROPERTY_ADDRESS]"))
    address, postcode = split_address_and_postcode(prop_block, prop_one)
    firm_name = _s(fields.get("[FIRM_TRADING_NAME]")) or _s(fields.get("[FIRM_REGISTERED_NAME]"))
    firm_pc = _s(fields.get("[FIRM_POSTCODE]"))
    firm_addr = firm_address_without_postcode(_s(fields.get("[FIRM_ADDRESS_BLOCK]")), firm_pc)
    fee_earner = _s(fields.get("[FEE_EARNER]"))
    case_ref = _s(fields.get("[CASE_REF]"))
    email = _s(fee_earner_email)

    if ref == "TA6":
        out: dict[str, Any] = {
            "propertyAddresses": prop_one or address.replace("\n", ", "),
            "Address": address,
            "Postcode 1": postcode,
            "Full name of the sellers 1": sellers,
            "Role - seller": True,
            "Name of the seller's solicitor's firm": firm_name,
            "Seller's solicitor address": firm_addr,
            "Seller's solicitor address postcode 1": firm_pc,
            "Seller's solicitor contact name": fee_earner,
            "Seller's solicitor email": email,
            "Seller's solicitor reference number": case_ref,
        }
        return {k: v for k, v in out.items() if v not in ("", None)}

    if ref == "TA7":
        # Leasehold form has property + seller name only (no solicitor block).
        out = {
            "propertyAddresses": prop_one or address.replace("\n", ", "),
            "Address": address,
            "Postcode 1": postcode,
            "Full name(s) of the seller(s)": sellers,
        }
        return {k: v for k, v in out.items() if v not in ("", None)}

    if ref == "TA10":
        out = {
            "propertyAddresses": prop_one or address.replace("\n", ", "),
            "propertyAddress": address.replace("\n", ", "),
            "propertyPostcode": postcode,
            "sellerFullName": sellers,
            "firmName": firm_name,
            "firmAddress": "\n".join(p for p in (firm_addr, firm_pc) if p),
            "mailFirmorPA": email,
            "matterReference": case_ref,
        }
        return {k: v for k, v in out.items() if v not in ("", None)}

    return {}


def prefill_ta_protocol_pdf(
    pdf_bytes: bytes,
    *,
    reference: str,
    fields: dict[str, str],
    fee_earner_email: str = "",
) -> bytes:
    """Prefill known header fields; leave the form fillable for the rest."""
    values = acroform_values_for_ta_reference(reference, fields, fee_earner_email=fee_earner_email)
    if not values:
        return pdf_bytes
    try:
        return fill_acroform(pdf_bytes, values, flatten=False)
    except Exception:
        log.exception("TA protocol PDF prefill failed reference=%s", reference)
        return pdf_bytes
