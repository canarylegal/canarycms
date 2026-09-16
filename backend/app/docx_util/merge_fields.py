"""Precedent merge field catalog and contact/letter merge helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.letter_salutation import (
    LetterSalutation,
    effective_letter_salutation,
    letter_salutation_body,
    primary_client_letter_dear_line,
    primary_client_letter_sign_off,
    resolve_letter_dear_line,
    resolve_letter_sign_off,
)

from ._text import _initial_letter, _s_str


def _precedent_code_suffix(slot: int) -> str:
    """Merge key suffix for additional clients 2–4, e.g. [TITLE] -> [TITLE_2]."""
    return f"_{slot}]"


def _merge_key_with_suffix(code: str, slot: int) -> str:
    if not code.startswith("[") or not code.endswith("]"):
        return code
    return code[:-1] + _precedent_code_suffix(slot)


# Name / company codes that are repeated for additional clients 2, 3 & 4 (see build_merge_fields).
_ADDITIONAL_CLIENT_NAME_CODES: tuple[str, ...] = (
    "[TITLE]",
    "[FIRST_NAME]",
    "[FIRST_INITIAL]",
    "[MIDDLE_NAME]",
    "[MIDDLE_INITIAL]",
    "[LAST_NAME]",
    "[LAST_INITIAL]",
    "[COMPANY_NAME]",
    "[TRADING_NAME]",
)

# Lawyer matter contacts are organisation-only; merge codes for the lawyer row are company / trading only.
_LAWYER_ROW_NAME_CODES: tuple[str, ...] = ("[COMPANY_NAME]", "[TRADING_NAME]")


PRECEDENT_CODES: dict[str, str] = {
    # Person
    "[TITLE]": "Title (e.g. Mr / Mrs / Dr)",
    "[FIRST_NAME]": "First name",
    "[FIRST_INITIAL]": "First initial (e.g. J)",
    "[MIDDLE_NAME]": "Middle name",
    "[MIDDLE_INITIAL]": "Middle initial",
    "[LAST_NAME]": "Surname",
    "[LAST_INITIAL]": "Surname initial",
    # Organisation
    "[COMPANY_NAME]": "Registered company name (optional)",
    "[TRADING_NAME]": "Trading name (required for organisations)",
    # Address (shared)
    "[ADDR1]": "Address line 1",
    "[ADDR2]": "Address line 2",
    "[ADDR3]": "Town / city",
    "[ADDR4]": "County",
    "[POSTCODE]": "Postcode",
    # Case / matter
    "[MATTER_DESCRIPTION]": "Matter description",
    "[CASE_REF]": "Case reference number",
    "[DATE]": "Date when the document is generated (DD/MM/YYYY)",
    "[FEE_EARNER]": "Fee earner display name (from the case fee earner)",
    "[FEE_EARNER_JOB_TITLE]": "Fee earner job title (from the case fee earner user)",
    "[FEE_EARNER_INITIALS]": "Fee earner initials (from the case fee earner user)",
    "[CONTACT_REF]": "Contact's reference (as stored in canary)",
    # Firm (Admin → Firm details); narrow scope — precedents / compose merge only for now.
    "[FIRM_TRADING_NAME]": "Firm trading name",
    "[FIRM_REGISTERED_NAME]": "Registered company name (optional)",
    "[FIRM_ADDR1]": "Firm address line 1",
    "[FIRM_ADDR2]": "Firm address line 2",
    "[FIRM_TOWN_CITY]": "Firm town / city",
    "[FIRM_COUNTY]": "Firm county",
    "[FIRM_POSTCODE]": "Firm postcode",
}

for _slot_num, _slot_label in ((2, "2nd"), (3, "3rd"), (4, "4th")):
    for _base_key in _ADDITIONAL_CLIENT_NAME_CODES:
        _suff_key = _merge_key_with_suffix(_base_key, _slot_num)
        PRECEDENT_CODES[_suff_key] = (
            f"{PRECEDENT_CODES[_base_key]} — additional client {_slot_num} "
            f"({_slot_label} 'Client' matter contact on the case, by date added)"
        )

for _li in range(1, 5):
    for _base_key in _LAWYER_ROW_NAME_CODES:
        _inner = _base_key[1:-1]
        _lk = f"[LAWYER_{_li}_{_inner}]"
        PRECEDENT_CODES[_lk] = (
            f"Lawyer {_li}: {PRECEDENT_CODES[_base_key]} "
            "(among 'Lawyers' matter contacts, by date added; lawyers are organisation contacts)"
        )

for _li in range(1, 5):
    for _cj in range(1, 5):
        for _base_key in _ADDITIONAL_CLIENT_NAME_CODES:
            _inner = _base_key[1:-1]
            _lk = f"[LAWYER_{_li}_CLIENT_{_cj}_{_inner}]"
            PRECEDENT_CODES[_lk] = f"Lawyer {_li}'s linked client {_cj}: {PRECEDENT_CODES[_base_key]}"

# Extra fields on each lawyer-linked client (name/company codes are in the loop above).
_LAWYER_LINKED_CLIENT_EXTRA: tuple[tuple[str, str], ...] = (
    ("NAME", "Display name on the contact card"),
    ("TYPE", "person or organisation"),
    ("EMAIL", "Email"),
    ("PHONE", "Phone"),
    ("ADDR1", "Address line 1"),
    ("ADDR2", "Address line 2"),
    ("ADDR3", "Town / city"),
    ("ADDR4", "County"),
    ("POSTCODE", "Postcode"),
    ("COUNTRY", "Country"),
    ("MATTER_REFERENCE", "Matter-specific reference on this case"),
    ("MATTER_CONTACT_TYPE", "Matter contact type label on this case"),
)

for _li in range(1, 5):
    for _cj in range(1, 5):
        for _inner, _lab in _LAWYER_LINKED_CLIENT_EXTRA:
            _lk = f"[LAWYER_{_li}_CLIENT_{_cj}_{_inner}]"
            PRECEDENT_CODES[_lk] = f"Lawyer {_li}'s linked client {_cj}: {_lab} (Case matter contact)"

# Shorthand: same values as [LAWYER_1_CLIENT_cj_*] (first Lawyers matter contact on the case, by date added).
_LAWYER_CONTACT_CLIENT_ALIAS_INNERS: tuple[str, ...] = tuple(
    c[1:-1] for c in _ADDITIONAL_CLIENT_NAME_CODES
) + tuple(x[0] for x in _LAWYER_LINKED_CLIENT_EXTRA)

for _cj in range(1, 5):
    for _inner in _LAWYER_CONTACT_CLIENT_ALIAS_INNERS:
        _lk = f"[LAWYER_CONTACT_CLIENT_{_cj}_{_inner}]"
        PRECEDENT_CODES[_lk] = (
            f"Same as [LAWYER_1_CLIENT_{_cj}_{_inner}]: first 'Lawyers' matter contact’s linked client {_cj} "
            "(by date added among Lawyers contacts)"
        )

# Explicit “selected in compose” contact (letter/document precedent); filled when a contact is chosen in the UI.
_CONTACT_COMPOSE_STATIC: tuple[tuple[str, str], ...] = (
    ("[CONTACT_NAME]", "Display name on the contact card"),
    ("[CONTACT_TYPE]", "person or organisation"),
    ("[CONTACT_EMAIL]", "Email"),
    ("[CONTACT_PHONE]", "Phone"),
    ("[CONTACT_ADDR1]", "Address line 1"),
    ("[CONTACT_ADDR2]", "Address line 2"),
    ("[CONTACT_ADDR3]", "Town / city"),
    ("[CONTACT_ADDR4]", "County"),
    ("[CONTACT_POSTCODE]", "Postcode"),
    ("[CONTACT_COUNTRY]", "Country"),
    (
        "[CONTACT_MATTER_REFERENCE]",
        "Matter-specific reference (case contact snapshot only; empty for a global directory contact)",
    ),
    (
        "[CONTACT_MATTER_CONTACT_TYPE]",
        "Matter contact type label on this case (case contact only; empty for a global directory contact)",
    ),
)
for _ck, _desc in _CONTACT_COMPOSE_STATIC:
    PRECEDENT_CODES[_ck] = (
        f"Selected contact for this compose: {_desc}. Empty if no contact was chosen in the dialogue."
    )

PRECEDENT_CODES["[CONTACT_LETTER_DEAR]"] = (
    "Selected compose contact: opening “Dear …,” from the contact’s letter salutation setting "
    "(informal first names, formal title+surname, Sir / Madam, Sirs, firm name, or custom). "
    "Empty if no contact was chosen in the dialogue."
)
PRECEDENT_CODES["[CONTACT_SALUTATION_BODY]"] = (
    "Selected compose contact: salutation text only (the part after “Dear ” before the comma), "
    "from the same salutation setting as [CONTACT_LETTER_DEAR]."
)
PRECEDENT_CODES["[CONTACT_LETTER_SIGN_OFF]"] = (
    "Selected compose contact: closing line (“Yours sincerely,” or “Yours faithfully,”) derived from "
    "the letter salutation — faithfully for Sir / Madam, Sir or Madam, and Sirs; sincerely for named "
    "addressees, firm name, and custom."
)
PRECEDENT_CODES["[SOLICITOR_OUR_CLIENT_LINE]"] = (
    "When the compose contact is a Lawyers matter contact: full line “Our Client: …” naming the firm’s "
    "client(s) on the matter. Empty when the letter is not to a lawyer (paragraph removed on merge)."
)
PRECEDENT_CODES["[SOLICITOR_YOUR_CLIENT_LINE]"] = (
    "When the compose contact is a Lawyers matter contact: full line “Your Client: …” naming the linked "
    "client on that lawyer row. Empty when the letter is not to a lawyer (paragraph removed on merge)."
)
PRECEDENT_CODES["[CONTACT_ORG_LINES]"] = (
    "Selected compose contact: trading name and registered company name with line breaks between non-empty "
    "parts only; empty for persons (avoids blank lines from separate [TRADING_NAME]/[COMPANY_NAME] paragraphs)."
)
PRECEDENT_CODES["[CONTACT_ADDRESS_BLOCK]"] = (
    "Selected compose contact: address lines with breaks between non-empty parts only "
    "(compact substitute for separate [CONTACT_ADDR1]… paragraphs)."
)
PRECEDENT_CODES["[CONTACT_ORG_AND_ADDRESS_BLOCK]"] = (
    "Selected compose contact: [CONTACT_ORG_LINES] and [CONTACT_ADDRESS_BLOCK] in one block — "
    "one line break between org and address sections only when both exist (no spare blank row for persons)."
)

PRECEDENT_CODES["[PRIMARY_CLIENT_LETTER_DEAR]"] = (
    "Primary letter addressee: opening “Dear …,” from the contact’s letter salutation setting "
    "(same contact as unsuffixed [ADDR1] / [ADDRESS_BLOCK]). "
    "When merge-all clients use informal salutation, first names are combined (e.g. Sarah and John)."
)
PRECEDENT_CODES["[PRIMARY_CLIENT_SALUTATION_BODY]"] = (
    "Primary addressee: salutation text only (after “Dear ”, before the comma), "
    "from the same setting as [PRIMARY_CLIENT_LETTER_DEAR]."
)
PRECEDENT_CODES["[PRIMARY_CLIENT_LETTER_SIGN_OFF]"] = (
    "Primary addressee: closing line from the same salutation rules as [CONTACT_LETTER_SIGN_OFF]."
)
PRECEDENT_CODES["[ORG_LINES]"] = (
    "Primary addressee (slot 1 Client): organisation trading + registered lines with breaks; "
    "empty for persons. Prefer one paragraph containing this token instead of separate [TRADING_NAME]/[COMPANY_NAME]."
)
PRECEDENT_CODES["[ADDRESS_BLOCK]"] = (
    "Primary addressee: address lines with breaks between non-empty parts only "
    "(substitute for separate [ADDR1]…[POSTCODE] paragraphs)."
)
PRECEDENT_CODES["[ORG_AND_ADDRESS_BLOCK]"] = (
    "Primary addressee: organisation lines (if any) plus address in one block — inserts a single line break "
    "between org and address only when both exist. Prefer this instead of separate [ORG_LINES] then [ADDRESS_BLOCK] "
    "paragraphs to avoid a blank line for person contacts when [ORG_LINES] is empty."
)

for _slot_num, _slot_label in ((2, "2nd"), (3, "3rd"), (4, "4th")):
    _olk = _merge_key_with_suffix("[ORG_LINES]", _slot_num)
    PRECEDENT_CODES[_olk] = (
        f"Organisation lines for {_slot_label} Client matter contact (merge-all or suffix slot); "
        "empty for persons."
    )
    _abk = _merge_key_with_suffix("[ADDRESS_BLOCK]", _slot_num)
    PRECEDENT_CODES[_abk] = f"Address block for {_slot_label} Client matter contact; omits blank lines."
    _oak = _merge_key_with_suffix("[ORG_AND_ADDRESS_BLOCK]", _slot_num)
    PRECEDENT_CODES[_oak] = (
        f"Combined org + address block for {_slot_label} Client contact (same rules as [ORG_AND_ADDRESS_BLOCK])."
    )

for _cn in range(1, 5):
    PRECEDENT_CODES[f"[CLIENT_{_cn}_LETTER_DEAR]"] = (
        f"Dear line for Client matter contact {_cn} (by client order on the matter), "
        "from that contact’s letter salutation setting. Use with merge-all or when listing multiple clients."
    )
    PRECEDENT_CODES[f"[CLIENT_{_cn}_SALUTATION_BODY]"] = (
        f"Salutation text only for Client matter contact {_cn} (same rules as [CLIENT_{_cn}_LETTER_DEAR])."
    )
    PRECEDENT_CODES[f"[CLIENT_{_cn}_LETTER_SIGN_OFF]"] = (
        f"Closing line for Client matter contact {_cn} (same rules as [CONTACT_LETTER_SIGN_OFF])."
    )

for _base_key in _ADDITIONAL_CLIENT_NAME_CODES:
    _inner = _base_key[1:-1]
    _cc_key = f"[CONTACT_{_inner}]"
    PRECEDENT_CODES[_cc_key] = (
        f"Selected contact for this compose: same field as [{_inner}] for person or organisation name parts; "
        f"always the contact picked in the dialogue (including when “merge all clients” fills [{_inner}] from another client)."
    )

PRECEDENT_CODES["[QUOTE_PROPERTY_VALUE]"] = "Property value used for banded fee scales (formatted GBP)."
PRECEDENT_CODES["[PROPERTY_ADDRESS_BLOCK]"] = (
    "Property address from the Property sub-menu (line breaks between parts)."
)
PRECEDENT_CODES["[PROPERTY_CHARGE_DATE]"] = "Charge / mortgage charge date from the Property sub-menu (dd/mm/yyyy)."
PRECEDENT_CODES["[PRIMARY_CLIENT_NAME]"] = (
    "Display name of the first Client matter contact on the case (by date added)."
)
PRECEDENT_CODES["[FIRM_ADDRESS_BLOCK]"] = "Firm address block (Admin → Firm details)."
PRECEDENT_CODES["[FIRM_CLIENT_BANK_ACCOUNT_NAME]"] = "Client bank account name (Admin → Firm details)."
PRECEDENT_CODES["[FIRM_CLIENT_BANK_SORT_CODE]"] = "Client bank sort code (Admin → Firm details)."
PRECEDENT_CODES["[FIRM_CLIENT_BANK_ACCOUNT_NUMBER]"] = (
    "Client bank account number (full number when stored, otherwise masked last four)."
)
PRECEDENT_CODES["[EXISTING_LENDER_NAME]"] = "Existing lender matter contact display name."
PRECEDENT_CODES["[EXISTING_LENDER_COMPANY_NAME]"] = "Existing lender registered company name."
PRECEDENT_CODES["[EXISTING_LENDER_TRADING_NAME]"] = "Existing lender trading name."
PRECEDENT_CODES["[EXISTING_LENDER_ADDRESS_BLOCK]"] = "Existing lender address block (organisation lines + address)."
PRECEDENT_CODES["[FEE_EARNER_SIGNATURE]"] = (
    "Fee earner signature image uploaded in User settings (size from signature scale, default 7 ≈ 2 in wide)."
)

# Image placeholders are resolved after text merge via inject_merge_code_images().
IMAGE_PRECEDENT_CODES: frozenset[str] = frozenset({"[FEE_EARNER_SIGNATURE]"})

for _qi in range(1, 26):
    _qtag = f"{_qi:02d}"
    PRECEDENT_CODES[f"[QUOTE_{_qtag}_LABEL]"] = f"Quote table row {_qi}: description."
    PRECEDENT_CODES[f"[QUOTE_{_qtag}_AMOUNT]"] = f"Quote table row {_qi}: main (net/inclusive) amount."
    PRECEDENT_CODES[f"[QUOTE_{_qtag}_VAT]"] = f"Quote table row {_qi}: VAT amount (Plus VAT lines)."
PRECEDENT_CODES["[QUOTE_MAIN_TOTAL]"] = "Sum of main-column amounts on item lines."
PRECEDENT_CODES["[QUOTE_VAT_TOTAL]"] = "Sum of VAT-column amounts on item lines."
PRECEDENT_CODES["[QUOTE_GRAND_TOTAL]"] = "Main column total plus VAT column total."
PRECEDENT_CODES["[INVOICE_NUMBER]"] = "Approved invoice number."
PRECEDENT_CODES["[INVOICE_DATE]"] = "Invoice date (approval date, e.g. 13 June 2026)."
PRECEDENT_CODES["[INVOICE_BILL_TO]"] = "Bill-to name on the invoice."
PRECEDENT_CODES["[INVOICE_NET_TOTAL]"] = "Sum of net amounts on invoice lines."
PRECEDENT_CODES["[INVOICE_VAT_TOTAL]"] = "Sum of VAT amounts on invoice lines."
PRECEDENT_CODES["[INVOICE_TOTAL]"] = "Invoice total (net plus VAT)."
for _ii in range(1, 26):
    _itag = f"{_ii:02d}"
    PRECEDENT_CODES[f"[INVOICE_{_itag}_TYPE]"] = f"Invoice table row {_ii}: line type (Fee, Disbursement, VAT)."
    PRECEDENT_CODES[f"[INVOICE_{_itag}_DESCRIPTION]"] = f"Invoice table row {_ii}: description."
    PRECEDENT_CODES[f"[INVOICE_{_itag}_NET]"] = f"Invoice table row {_ii}: net amount."
    PRECEDENT_CODES[f"[INVOICE_{_itag}_VAT]"] = f"Invoice table row {_ii}: VAT amount."
    PRECEDENT_CODES[f"[INVOICE_{_itag}_TOTAL]"] = f"Invoice table row {_ii}: line total (net plus VAT)."
PRECEDENT_CODES["[COMPLETION_DATE]"] = "Completion statement date (e.g. 13 June 2026)."
PRECEDENT_CODES["[COMPLETION_TOTAL_DEBIT]"] = "Sum of debit column amounts."
PRECEDENT_CODES["[COMPLETION_TOTAL_CREDIT]"] = "Sum of credit column amounts."
PRECEDENT_CODES["[COMPLETION_BALANCE_LABEL]"] = "Balance label (due from / due to client)."
PRECEDENT_CODES["[COMPLETION_BALANCE_AMOUNT]"] = "Balance amount (absolute value)."
for _ci in range(1, 51):
    _ctag = f"{_ci:02d}"
    PRECEDENT_CODES[f"[COMPLETION_{_ctag}_DESCRIPTION]"] = f"Completion table row {_ci}: category or item description."
    PRECEDENT_CODES[f"[COMPLETION_{_ctag}_DEBIT]"] = f"Completion table row {_ci}: debit amount."
    PRECEDENT_CODES[f"[COMPLETION_{_ctag}_CREDIT]"] = f"Completion table row {_ci}: credit amount."


def _core_name_company_for_contact(contact: Any | None) -> dict[str, str]:
    """Nine merge keys shared by primary and additional-client slots."""

    if not contact:
        return {k: "" for k in _ADDITIONAL_CLIENT_NAME_CODES}

    contact_type = _s_str(getattr(contact, "type", "person"))
    first = _s_str(getattr(contact, "first_name", None))
    middle = _s_str(getattr(contact, "middle_name", None))
    last = _s_str(getattr(contact, "last_name", None))

    company = _s_str(getattr(contact, "company_name", None))
    if not company and contact_type == "organisation":
        company = _s_str(getattr(contact, "name", None))

    return {
        "[TITLE]": _s_str(getattr(contact, "title", None)),
        "[FIRST_NAME]": first,
        "[FIRST_INITIAL]": _initial_letter(first),
        "[MIDDLE_NAME]": middle,
        "[MIDDLE_INITIAL]": _initial_letter(middle),
        "[LAST_NAME]": last,
        "[LAST_INITIAL]": _initial_letter(last),
        "[COMPANY_NAME]": company,
        "[TRADING_NAME]": _s_str(getattr(contact, "trading_name", None)),
    }


def _contact_type_str(contact: Any) -> str:
    t = getattr(contact, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        return str(t.value)
    return str(t)


def _letter_dear_line(contact: Any | None, *, informal_name_contacts: list[Any] | None = None) -> str:
    return resolve_letter_dear_line(contact, informal_name_contacts=informal_name_contacts)


def _salutation_body_line(contact: Any | None, *, informal_name_contacts: list[Any] | None = None) -> str:
    return letter_salutation_body(contact, informal_name_contacts=informal_name_contacts)


def _letter_sign_off_line(contact: Any | None) -> str:
    return resolve_letter_sign_off(contact)


def _org_lines_block(contact: Any | None) -> str:
    """Trading + registered company lines for organisations only; embedded newlines, no trailing blanks."""

    if not contact:
        return ""
    if _contact_type_str(contact) != "organisation":
        return ""
    tr = _s_str(getattr(contact, "trading_name", None))
    reg = _s_str(getattr(contact, "company_name", None))
    return "\n".join(x for x in (tr, reg) if x)


def _address_block_lines(contact: Any | None) -> str:
    """Single-string address with line breaks; skips empty parts (no blank lines)."""

    if not contact:
        return ""
    parts = (
        _s_str(getattr(contact, "address_line1", None)),
        _s_str(getattr(contact, "address_line2", None)),
        _s_str(getattr(contact, "city", None)),
        _s_str(getattr(contact, "county", None)),
        _s_str(getattr(contact, "postcode", None)),
    )
    return "\n".join(p for p in parts if p)


def _org_and_address_block(contact: Any | None) -> str:
    """Organisation lines plus address in one string; no extra gap when org is empty (typical for persons)."""

    org = _org_lines_block(contact)
    addr = _address_block_lines(contact)
    if org and addr:
        return f"{org}\n{addr}"
    return org or addr


def _fill_full_client_composite_slots(out: dict[str, str], oc: list[Any]) -> None:
    """ORG_LINES / ADDRESS_BLOCK / dear lines for each Client slot (merge-all layout)."""

    for i, cc in enumerate(oc[:4]):
        slot = i + 1
        org_b = _org_lines_block(cc)
        addr_b = _address_block_lines(cc)
        dear = _letter_dear_line(cc)
        sal_body = _salutation_body_line(cc)
        sign_off = _letter_sign_off_line(cc)
        out[f"[CLIENT_{slot}_LETTER_DEAR]"] = dear
        out[f"[CLIENT_{slot}_SALUTATION_BODY]"] = sal_body
        out[f"[CLIENT_{slot}_LETTER_SIGN_OFF]"] = sign_off
        if slot == 1:
            out["[ORG_LINES]"] = org_b
            out["[ADDRESS_BLOCK]"] = addr_b
            out["[ORG_AND_ADDRESS_BLOCK]"] = _org_and_address_block(cc)
            primary_dear = primary_client_letter_dear_line(oc)
            out["[PRIMARY_CLIENT_LETTER_DEAR]"] = primary_dear
            out["[PRIMARY_CLIENT_LETTER_SIGN_OFF]"] = primary_client_letter_sign_off(oc)
            informal_contacts = (
                oc
                if len(oc) > 1
                and effective_letter_salutation(cc) == LetterSalutation.dear_first_name_informal.value
                else None
            )
            out["[PRIMARY_CLIENT_SALUTATION_BODY]"] = _salutation_body_line(
                cc,
                informal_name_contacts=informal_contacts,
            )
        else:
            out[_merge_key_with_suffix("[ORG_LINES]", slot)] = org_b
            out[_merge_key_with_suffix("[ADDRESS_BLOCK]", slot)] = addr_b
            out[_merge_key_with_suffix("[ORG_AND_ADDRESS_BLOCK]", slot)] = _org_and_address_block(cc)


def _set_primary_addressee_composites(out: dict[str, str], contact: Any | None) -> None:
    """Primary unsuffixed address/org composites from the letter addressee row."""

    if contact is None:
        return
    out["[ORG_LINES]"] = _org_lines_block(contact)
    out["[ADDRESS_BLOCK]"] = _address_block_lines(contact)
    out["[ORG_AND_ADDRESS_BLOCK]"] = _org_and_address_block(contact)
    out["[PRIMARY_CLIENT_LETTER_DEAR]"] = _letter_dear_line(contact)
    out["[PRIMARY_CLIENT_SALUTATION_BODY]"] = _salutation_body_line(contact)
    out["[PRIMARY_CLIENT_LETTER_SIGN_OFF]"] = _letter_sign_off_line(contact)


def _fill_client_dear_lines_and_secondary_composites(out: dict[str, str], oc: list[Any]) -> None:
    """Per-slot Dear lines; suffixed org/address for clients 2–4 (slot 1 primary comes from addressee)."""

    for i, cc in enumerate(oc[:4]):
        slot = i + 1
        out[f"[CLIENT_{slot}_LETTER_DEAR]"] = _letter_dear_line(cc)
        out[f"[CLIENT_{slot}_SALUTATION_BODY]"] = _salutation_body_line(cc)
        out[f"[CLIENT_{slot}_LETTER_SIGN_OFF]"] = _letter_sign_off_line(cc)
        if slot >= 2:
            out[_merge_key_with_suffix("[ORG_LINES]", slot)] = _org_lines_block(cc)
            out[_merge_key_with_suffix("[ADDRESS_BLOCK]", slot)] = _address_block_lines(cc)
            out[_merge_key_with_suffix("[ORG_AND_ADDRESS_BLOCK]", slot)] = _org_and_address_block(cc)


def _lawyer_linked_client_extra_map(contact: Any | None) -> dict[str, str]:
    """Extra merge fields for a lawyer-linked CaseContact (beyond the nine name/company keys)."""

    if not contact:
        return {x[0]: "" for x in _LAWYER_LINKED_CLIENT_EXTRA}
    return {
        "NAME": _s_str(getattr(contact, "name", None)),
        "TYPE": _contact_type_str(contact),
        "EMAIL": _s_str(getattr(contact, "email", None)),
        "PHONE": _s_str(getattr(contact, "phone", None)),
        "ADDR1": _s_str(getattr(contact, "address_line1", None)),
        "ADDR2": _s_str(getattr(contact, "address_line2", None)),
        "ADDR3": _s_str(getattr(contact, "city", None)),
        "ADDR4": _s_str(getattr(contact, "county", None)),
        "POSTCODE": _s_str(getattr(contact, "postcode", None)),
        "COUNTRY": _s_str(getattr(contact, "country", None)),
        "MATTER_REFERENCE": _s_str(getattr(contact, "matter_contact_reference", None)),
        "MATTER_CONTACT_TYPE": _s_str(getattr(contact, "matter_contact_type", None)),
    }


def _empty_precedent_field_map() -> dict[str, str]:
    return {k: "" for k in PRECEDENT_CODES}


def _apply_lawyer_merge_slots(
    out: dict[str, str],
    lawyer_slots: list[tuple[Any, list[Any]] | None] | None,
) -> None:
    if not lawyer_slots:
        return
    for i in range(min(4, len(lawyer_slots))):
        slot = lawyer_slots[i]
        if not slot:
            continue
        law_cc, client_list = slot
        li = i + 1
        law_core = _core_name_company_for_contact(law_cc)
        for merge_key in _LAWYER_ROW_NAME_CODES:
            inner = merge_key[1:-1]
            out[f"[LAWYER_{li}_{inner}]"] = law_core.get(merge_key, "")
        for j, cli in enumerate((client_list or [])[:4]):
            cj = j + 1
            ccore = _core_name_company_for_contact(cli)
            for merge_key, val in ccore.items():
                inner = merge_key[1:-1]
                out[f"[LAWYER_{li}_CLIENT_{cj}_{inner}]"] = val
            extras = _lawyer_linked_client_extra_map(cli)
            for inner, val in extras.items():
                out[f"[LAWYER_{li}_CLIENT_{cj}_{inner}]"] = val
            if li == 1:
                for merge_key, val in ccore.items():
                    inner = merge_key[1:-1]
                    out[f"[LAWYER_CONTACT_CLIENT_{cj}_{inner}]"] = val
                for inner, val in extras.items():
                    out[f"[LAWYER_CONTACT_CLIENT_{cj}_{inner}]"] = val


def _our_clients_display_for_solicitor_letter(
    ordered_client_contacts: list[Any] | None,
    *,
    merge_all_clients: bool,
) -> str:
    names = [
        _s_str(getattr(cc, "name", None))
        for cc in (ordered_client_contacts or [])[:4]
        if _s_str(getattr(cc, "name", None))
    ]
    if not names:
        return ""
    if merge_all_clients and len(names) > 1:
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f" and {names[-1]}"
    return names[0]


def _your_client_display_for_solicitor_letter(
    compose_contact: Any | None,
    lawyer_slots: list[tuple[Any, list[Any]] | None] | None,
) -> str:
    from app.matter_contact_constants import LAWYERS_SLUG, normalize_matter_contact_type_slug

    if compose_contact is None:
        return ""
    if normalize_matter_contact_type_slug(getattr(compose_contact, "matter_contact_type", None)) != LAWYERS_SLUG:
        return ""
    target_id = getattr(compose_contact, "id", None)
    for slot in lawyer_slots or []:
        if not slot:
            continue
        law_cc, clients = slot
        if getattr(law_cc, "id", None) != target_id:
            continue
        for cli in (clients or [])[:1]:
            name = _s_str(getattr(cli, "name", None))
            if name:
                return name
        return ""
    return ""


def _fill_solicitor_correspondence_lines(
    out: dict[str, str],
    *,
    compose_contact: Any | None,
    ordered_client_contacts: list[Any] | None,
    lawyer_slots: list[tuple[Any, list[Any]] | None] | None,
    merge_all_clients: bool,
) -> None:
    from app.matter_contact_constants import LAWYERS_SLUG, normalize_matter_contact_type_slug

    is_solicitor_letter = (
        compose_contact is not None
        and normalize_matter_contact_type_slug(getattr(compose_contact, "matter_contact_type", None))
        == LAWYERS_SLUG
    )
    if not is_solicitor_letter:
        out["[SOLICITOR_OUR_CLIENT_LINE]"] = ""
        out["[SOLICITOR_YOUR_CLIENT_LINE]"] = ""
        return
    our = _our_clients_display_for_solicitor_letter(
        ordered_client_contacts,
        merge_all_clients=merge_all_clients,
    )
    your = _your_client_display_for_solicitor_letter(compose_contact, lawyer_slots)
    out["[SOLICITOR_OUR_CLIENT_LINE]"] = f"Our Client: {our}" if our else ""
    out["[SOLICITOR_YOUR_CLIENT_LINE]"] = f"Your Client: {your}" if your else ""


def _fill_compose_selected_contact_codes(out: dict[str, str], contact: Any | None) -> None:
    """Fill ``[CONTACT_*]`` keys from the contact chosen in the compose dialogue (if any)."""

    if not contact:
        return
    core = _core_name_company_for_contact(contact)
    for merge_key in _ADDITIONAL_CLIENT_NAME_CODES:
        inner = merge_key[1:-1]
        out[f"[CONTACT_{inner}]"] = core.get(merge_key, "")
    out["[CONTACT_NAME]"] = _s_str(getattr(contact, "name", None))
    out["[CONTACT_TYPE]"] = _contact_type_str(contact)
    out["[CONTACT_EMAIL]"] = _s_str(getattr(contact, "email", None))
    out["[CONTACT_PHONE]"] = _s_str(getattr(contact, "phone", None))
    out["[CONTACT_ADDR1]"] = _s_str(getattr(contact, "address_line1", None))
    out["[CONTACT_ADDR2]"] = _s_str(getattr(contact, "address_line2", None))
    out["[CONTACT_ADDR3]"] = _s_str(getattr(contact, "city", None))
    out["[CONTACT_ADDR4]"] = _s_str(getattr(contact, "county", None))
    out["[CONTACT_POSTCODE]"] = _s_str(getattr(contact, "postcode", None))
    out["[CONTACT_COUNTRY]"] = _s_str(getattr(contact, "country", None))
    out["[CONTACT_MATTER_REFERENCE]"] = _s_str(getattr(contact, "matter_contact_reference", None))
    out["[CONTACT_MATTER_CONTACT_TYPE]"] = _s_str(getattr(contact, "matter_contact_type", None))
    out["[CONTACT_LETTER_DEAR]"] = _letter_dear_line(contact)
    out["[CONTACT_SALUTATION_BODY]"] = _salutation_body_line(contact)
    out["[CONTACT_LETTER_SIGN_OFF]"] = _letter_sign_off_line(contact)
    out["[CONTACT_ORG_LINES]"] = _org_lines_block(contact)
    out["[CONTACT_ADDRESS_BLOCK]"] = _address_block_lines(contact)
    out["[CONTACT_ORG_AND_ADDRESS_BLOCK]"] = _org_and_address_block(contact)


def _fill_merge_all_clients_contact_letter_codes(out: dict[str, str], oc: list[Any]) -> None:
    """Fill ``[CONTACT_LETTER_*]`` when merging all clients (no single compose contact)."""

    if not oc:
        return
    first = oc[0]
    out["[CONTACT_LETTER_DEAR]"] = primary_client_letter_dear_line(oc)
    out["[CONTACT_LETTER_SIGN_OFF]"] = primary_client_letter_sign_off(oc)
    informal_contacts = (
        oc
        if len(oc) > 1
        and effective_letter_salutation(first) == LetterSalutation.dear_first_name_informal.value
        else None
    )
    out["[CONTACT_SALUTATION_BODY]"] = _salutation_body_line(
        first,
        informal_name_contacts=informal_contacts,
    )


def build_merge_fields(
    case: Any,
    fee_earner_name: str = "",
    fee_earner_job_title: str = "",
    fee_earner_initials: str = "",
    merge_date: date | None = None,
    *,
    merge_all_clients: bool = False,
    ordered_client_contacts: list[Any] | None = None,
    selected_contact: Any | None = None,
    selected_client_slot: int | None = None,
    lawyer_slots: list[tuple[Any, list[Any]] | None] | None = None,
    compose_selected_contact: Any | None = None,
    firm: Any | None = None,
) -> dict[str, str]:
    """Build precedent code→value dict.

    * **merge_all_clients** — Fill client 1 from ``ordered_client_contacts[0]`` into unsuffixed
      keys and ``[ADDR*]``; clients 2–4 into ``[TITLE_2]`` … ``[TRADING_NAME_4]``.
      ``[CONTACT_REF]`` is taken from the first client row.

    * **Single Client matter contact** (``selected_client_slot`` 1–4) — Fill only that client’s
      name/company keys (slot 1 unsuffixed; slots 2–4 use ``_2`` … ``_4``). Address and
      ``[CONTACT_REF]`` come from ``selected_contact``.

    * **Global contact or non-Client matter contact** (``selected_client_slot`` is None) — Fill
      unsuffixed name and address keys only; suffixed client keys stay empty.

    * **compose_selected_contact** — When set (the contact chosen in the compose UI), fills
      ``[CONTACT_*]`` codes from that row even when ``merge_all_clients`` is True, so templates
      can address the picked contact separately from unsuffixed client merge keys.

    * **Composite tokens** — ``[ORG_LINES]``, ``[ADDRESS_BLOCK]``, ``[ORG_AND_ADDRESS_BLOCK]`` (combined, no blank row
      when org is empty), suffixed ``[ORG_LINES_2]`` … ``[ORG_AND_ADDRESS_BLOCK_4]``, ``[PRIMARY_CLIENT_LETTER_DEAR]``,
      ``[CLIENT_1_LETTER_DEAR]`` … ``[CLIENT_4_LETTER_DEAR]``, and compose-only ``[CONTACT_LETTER_DEAR]``,
      ``[CONTACT_ORG_LINES]``, ``[CONTACT_ADDRESS_BLOCK]``, ``[CONTACT_ORG_AND_ADDRESS_BLOCK]``
      pack multiple lines into one placeholder with internal line breaks so merged letters do not
      retain empty paragraphs when parts are blank.
    """

    out = _empty_precedent_field_map()

    def finalize(m: dict[str, str]) -> dict[str, str]:
        if merge_all_clients:
            oc_local = [c for c in (ordered_client_contacts or [])][:4]
            if oc_local:
                _fill_merge_all_clients_contact_letter_codes(m, oc_local)
        _apply_lawyer_merge_slots(m, lawyer_slots)
        _fill_compose_selected_contact_codes(m, compose_selected_contact)
        _fill_solicitor_correspondence_lines(
            m,
            compose_contact=compose_selected_contact,
            ordered_client_contacts=ordered_client_contacts,
            lawyer_slots=lawyer_slots,
            merge_all_clients=merge_all_clients,
        )
        return m

    matter_desc = _s_str(getattr(case, "title", None)) if case else ""
    case_ref = _s_str(getattr(case, "case_number", None)) if case else ""
    d = merge_date or date.today()
    date_str = d.strftime("%d/%m/%Y")

    out["[MATTER_DESCRIPTION]"] = matter_desc
    out["[CASE_REF]"] = case_ref
    out["[DATE]"] = date_str
    out["[FEE_EARNER]"] = fee_earner_name
    out["[FEE_EARNER_JOB_TITLE]"] = fee_earner_job_title
    out["[FEE_EARNER_INITIALS]"] = _s_str(fee_earner_initials)

    if firm is not None:
        out["[FIRM_TRADING_NAME]"] = _s_str(getattr(firm, "trading_name", None))
        out["[FIRM_REGISTERED_NAME]"] = _s_str(getattr(firm, "registered_company_name", None))
        out["[FIRM_ADDR1]"] = _s_str(getattr(firm, "addr_line1", None))
        out["[FIRM_ADDR2]"] = _s_str(getattr(firm, "addr_line2", None))
        out["[FIRM_TOWN_CITY]"] = _s_str(getattr(firm, "town_city", None))
        out["[FIRM_COUNTY]"] = _s_str(getattr(firm, "county", None))
        out["[FIRM_POSTCODE]"] = _s_str(getattr(firm, "postcode", None))
        firm_addr_parts = (
            out["[FIRM_ADDR1]"],
            out["[FIRM_ADDR2]"],
            out["[FIRM_TOWN_CITY]"],
            out["[FIRM_COUNTY]"],
            out["[FIRM_POSTCODE]"],
        )
        out["[FIRM_ADDRESS_BLOCK]"] = "\n".join(p for p in firm_addr_parts if p)
        out["[FIRM_CLIENT_BANK_ACCOUNT_NAME]"] = _s_str(getattr(firm, "client_bank_account_name", None))
        out["[FIRM_CLIENT_BANK_SORT_CODE]"] = _s_str(getattr(firm, "client_bank_sort_code", None))
        acct_full = _s_str(getattr(firm, "client_bank_account_number", None))
        if acct_full:
            out["[FIRM_CLIENT_BANK_ACCOUNT_NUMBER]"] = acct_full
        else:
            last4 = _s_str(getattr(firm, "client_bank_account_number_last4", None))
            out["[FIRM_CLIENT_BANK_ACCOUNT_NUMBER]"] = f"•••• {last4}" if last4 else ""

    oc = [c for c in (ordered_client_contacts or [])][:4]
    if oc:
        out["[PRIMARY_CLIENT_NAME]"] = _s_str(getattr(oc[0], "name", None))

    if merge_all_clients:
        for i, cc in enumerate(oc):
            core = _core_name_company_for_contact(cc)
            if i == 0:
                for k, v in core.items():
                    out[k] = v
                out["[ADDR1]"] = _s_str(getattr(cc, "address_line1", None))
                out["[ADDR2]"] = _s_str(getattr(cc, "address_line2", None))
                out["[ADDR3]"] = _s_str(getattr(cc, "city", None))
                out["[ADDR4]"] = _s_str(getattr(cc, "county", None))
                out["[POSTCODE]"] = _s_str(getattr(cc, "postcode", None))
                out["[CONTACT_REF]"] = _s_str(getattr(cc, "matter_contact_reference", None))
            else:
                slot = i + 1
                for k, v in core.items():
                    out[_merge_key_with_suffix(k, slot)] = v
        _fill_full_client_composite_slots(out, oc)
        return finalize(out)

    if selected_contact is None:
        return finalize(out)

    contact_ref = _s_str(getattr(selected_contact, "matter_contact_reference", None))
    out["[ADDR1]"] = _s_str(getattr(selected_contact, "address_line1", None))
    out["[ADDR2]"] = _s_str(getattr(selected_contact, "address_line2", None))
    out["[ADDR3]"] = _s_str(getattr(selected_contact, "city", None))
    out["[ADDR4]"] = _s_str(getattr(selected_contact, "county", None))
    out["[POSTCODE]"] = _s_str(getattr(selected_contact, "postcode", None))

    if selected_client_slot is None or not (1 <= selected_client_slot <= 4):
        core = _core_name_company_for_contact(selected_contact)
        for k, v in core.items():
            out[k] = v
        out["[CONTACT_REF]"] = contact_ref
        _set_primary_addressee_composites(out, selected_contact)
        if oc:
            _fill_client_dear_lines_and_secondary_composites(out, oc)
        else:
            out["[CLIENT_1_LETTER_DEAR]"] = _letter_dear_line(selected_contact)
            out["[CLIENT_1_LETTER_SIGN_OFF]"] = _letter_sign_off_line(selected_contact)
        return finalize(out)

    idx = selected_client_slot - 1
    cc = oc[idx] if idx < len(oc) else None
    if cc is None:
        out["[CONTACT_REF]"] = contact_ref
        _set_primary_addressee_composites(out, selected_contact)
        if oc:
            _fill_client_dear_lines_and_secondary_composites(out, oc)
        else:
            out["[CLIENT_1_LETTER_DEAR]"] = _letter_dear_line(selected_contact)
            out["[CLIENT_1_LETTER_SIGN_OFF]"] = _letter_sign_off_line(selected_contact)
        return finalize(out)

    core = _core_name_company_for_contact(cc)
    if selected_client_slot == 1:
        for k, v in core.items():
            out[k] = v
    else:
        for k, v in core.items():
            out[_merge_key_with_suffix(k, selected_client_slot)] = v

    out["[CONTACT_REF]"] = contact_ref
    _set_primary_addressee_composites(out, selected_contact)
    if oc:
        _fill_client_dear_lines_and_secondary_composites(out, oc)
    else:
        out["[CLIENT_1_LETTER_DEAR]"] = _letter_dear_line(selected_contact)
        out["[CLIENT_1_LETTER_SIGN_OFF]"] = _letter_sign_off_line(selected_contact)
    return finalize(out)

def _property_payload_address_lines(payload: dict[str, Any]) -> list[str]:
    if payload.get("is_non_postal"):
        raw = payload.get("free_lines") or []
        if not isinstance(raw, list):
            return []
        return [_s_str(x) for x in raw if _s_str(x)]
    uk = payload.get("uk") or {}
    if not isinstance(uk, dict):
        uk = {}
    parts = (
        _s_str(uk.get("line1")),
        _s_str(uk.get("line2")),
        _s_str(uk.get("town")),
        _s_str(uk.get("county")),
        _s_str(uk.get("postcode")),
        _s_str(uk.get("country")),
    )
    return [p for p in parts if p]


def property_merge_fields(db: Session, case_id: uuid.UUID) -> dict[str, str]:
    """Merge codes from Property sub-menu (address, existing lender + charge date)."""
    from app.models import CaseContact, CasePropertyDetails

    out: dict[str, str] = {
        "[PROPERTY_ADDRESS_BLOCK]": "",
        "[PROPERTY_CHARGE_DATE]": "",
        "[EXISTING_LENDER_NAME]": "",
        "[EXISTING_LENDER_COMPANY_NAME]": "",
        "[EXISTING_LENDER_TRADING_NAME]": "",
        "[EXISTING_LENDER_ADDRESS_BLOCK]": "",
    }
    row = db.get(CasePropertyDetails, case_id)
    if not row or not isinstance(row.payload, dict):
        return out
    payload = row.payload
    addr_lines = _property_payload_address_lines(payload)
    if addr_lines:
        out["[PROPERTY_ADDRESS_BLOCK]"] = "\n".join(addr_lines)
    charge_raw = _s_str(payload.get("charge_date"))
    if charge_raw:
        try:
            from datetime import date as date_cls

            d = date_cls.fromisoformat(charge_raw[:10])
            out["[PROPERTY_CHARGE_DATE]"] = d.strftime("%d/%m/%Y")
        except ValueError:
            out["[PROPERTY_CHARGE_DATE]"] = charge_raw
    lender_id = payload.get("existing_lender_case_contact_id")
    if not lender_id:
        return out
    try:
        lid = uuid.UUID(str(lender_id))
    except ValueError:
        return out
    lender = db.get(CaseContact, lid)
    if not lender or lender.case_id != case_id:
        return out
    core = _core_name_company_for_contact(lender)
    out["[EXISTING_LENDER_NAME]"] = _s_str(getattr(lender, "name", None))
    out["[EXISTING_LENDER_COMPANY_NAME]"] = core.get("[COMPANY_NAME]", "")
    out["[EXISTING_LENDER_TRADING_NAME]"] = core.get("[TRADING_NAME]", "")
    out["[EXISTING_LENDER_ADDRESS_BLOCK]"] = _org_and_address_block(lender)
    return out

