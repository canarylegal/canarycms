"""Plain-text templates for automated internal and external alerts."""

from __future__ import annotations


def _firm_line(firm_name: str) -> str:
    name = (firm_name or "").strip()
    return name or "Your firm"


def _html_email(*, firm_name: str, paragraphs: list[str], bullets: list[str] | None = None) -> str:
    parts = [
        '<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#1a1a2e;">',
    ]
    for p in paragraphs:
        parts.append(f"<p>{_escape_html(p)}</p>")
    if bullets:
        parts.append("<ul>")
        for b in bullets:
            parts.append(f"<li>{_escape_html(b)}</li>")
        parts.append("</ul>")
    parts.append(f'<p style="color:#666;margin-top:1.5em;">— {_escape_html(_firm_line(firm_name))}</p>')
    parts.append("</body></html>")
    return "".join(parts)


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_cta_button(url: str, label: str) -> str:
    safe_url = _escape_html(url)
    safe_label = _escape_html(label)
    return (
        '<p style="margin:1.25em 0 0.75em;">'
        f'<a href="{safe_url}" style="display:inline-block;padding:12px 22px;background-color:#0891b2;'
        'color:#ffffff;text-decoration:none;font-weight:600;border-radius:8px;font-size:15px;">'
        f"{safe_label}</a></p>"
    )


def _html_fallback_link(url: str) -> str:
    return (
        '<p style="font-size:13px;color:#64748b;margin:0;">'
        "If the button does not work, open this link:<br>"
        f'<a href="{_escape_html(url)}" style="color:#0891b2;">{_escape_html(url)}</a>'
        "</p>"
    )


def _html_highlight_code(label: str, code: str) -> str:
    return (
        f'<p style="margin:1em 0 0.5em;font-size:14px;color:#334155;">{_escape_html(label)}</p>'
        '<p style="margin:0 0 1em;font-family:ui-monospace,monospace;font-size:22px;font-weight:700;'
        f'letter-spacing:0.08em;color:#0f172a;background:#f1f5f9;padding:12px 16px;border-radius:8px;'
        f'display:inline-block;">{_escape_html(code)}</p>'
    )


def _html_bullet_list(items: list[str]) -> str:
    lis = "".join(f"<li>{_escape_html(item)}</li>" for item in items)
    return f'<ul style="margin:0.75em 0 1em;padding-left:1.25em;color:#334155;">{lis}</ul>'


def _html_info_block(*, title: str, lines: list[str]) -> str:
    body = "".join(
        f'<p style="margin:0 0 6px;color:#334155;">{_escape_html(line)}</p>' for line in lines
    )
    return (
        f'<p style="margin:0 0 8px;font-weight:600;color:#0f172a;">{_escape_html(title)}</p>'
        f"{body}"
    )


def _html_email_shell(*, inner_html: str, firm_name: str) -> str:
    return (
        '<!DOCTYPE html><html><body style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        'line-height:1.5;color:#0f172a;max-width:560px;">'
        f"{inner_html}"
        f'<p style="color:#666;margin-top:1.5em;">— {_escape_html(_firm_line(firm_name))}</p>'
        "</body></html>"
    )


def calendar_event_reminder(*, title: str, anchor_label: str) -> tuple[str, str]:
    subject = f"Calendar reminder: {title or 'Event'}"
    body = "\n".join(
        [
            "This is a reminder for your Canary calendar event:",
            "",
            title or "(no title)",
            "",
            f"Event date (UTC): {anchor_label}",
            "",
            "You are receiving this because e-mail alerts are enabled for this event in Canary.",
        ]
    )
    return subject, body


def portal_staff_upload(
    *,
    firm_name: str,
    contact_name: str,
    area_label: str,
    filename: str,
) -> tuple[str, str, str]:
    subject = f"Portal upload: {filename}"
    body = "\n".join(
        [
            f"{contact_name} uploaded a file via Canary Portal.",
            "",
            f"Area: {area_label}",
            f"File: {filename}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(
            title=f"{contact_name} uploaded a file via Canary Portal",
            lines=[f"Area: {area_label}", f"File: {filename}"],
        ),
    )
    return subject, body, html


def portal_contact_access_granted(
    *,
    firm_name: str,
    contact_name: str,
    portal_url: str,
    access_code: str,
) -> tuple[str, str, str]:
    subject = f"Canary Portal access — {_firm_line(firm_name)}"
    cta_label = "Open client portal"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            "You can access your documents using Canary Portal.",
            "",
            f"{cta_label}: {portal_url}",
            f"Access code: {access_code}",
            "",
            "Keep this code confidential. Contact us if you need a new code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            "<p>You can access your documents using Canary Portal.</p>"
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
            f"{_html_highlight_code('Your access code', access_code)}"
            '<p style="font-size:13px;color:#64748b;margin:0;">'
            "Keep this code confidential. Contact us if you need a new code."
            "</p>"
        ),
    )
    return subject, body, html


def password_reset_email(
    *,
    firm_name: str,
    display_name: str,
    reset_url: str,
) -> tuple[str, str]:
    subject = f"Reset your password — {_firm_line(firm_name)}"
    body = "\n".join(
        [
            f"Dear {display_name},",
            "",
            "We received a request to reset your Canary password.",
            "",
            f"Reset link (valid for one hour): {reset_url}",
            "",
            "If you did not request this, you can ignore this e-mail. Your password will not change until you use the link above.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    return subject, body


def portal_contact_folder_granted(
    *,
    firm_name: str,
    contact_name: str,
    area_label: str,
    portal_url: str,
) -> tuple[str, str, str]:
    subject = f"Documents shared with you — {_firm_line(firm_name)}"
    cta_label = "View documents"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Documents have been shared with you: {area_label}",
            "",
            f"{cta_label}: {portal_url}",
            "",
            "Sign in with your personal access code or e-mail sign-in code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            f"<p>Documents have been shared with you: <strong>{_escape_html(area_label)}</strong></p>"
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
            '<p style="font-size:13px;color:#64748b;margin:0;">'
            "Sign in with your personal access code or e-mail sign-in code."
            "</p>"
        ),
    )
    return subject, body, html


def portal_contact_files_added(
    *,
    firm_name: str,
    contact_name: str,
    area_label: str,
    filenames: list[str],
    portal_url: str,
) -> tuple[str, str, str]:
    subject = f"New documents — {area_label}"
    cta_label = "View documents"
    lines = [
        f"Dear {contact_name},",
        "",
        f"New file(s) are available in {area_label}:",
        "",
    ]
    for fn in filenames:
        lines.append(f"• {fn}")
    lines.extend(
        [
            "",
            f"{cta_label}: {portal_url}",
            "",
            "Sign in with your access code or e-mail sign-in code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    body = "\n".join(lines)
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            f"<p>New file(s) are available in <strong>{_escape_html(area_label)}</strong>:</p>"
            f"{_html_bullet_list(filenames)}"
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
            '<p style="font-size:13px;color:#64748b;margin:0;">'
            "Sign in with your access code or e-mail sign-in code."
            "</p>"
        ),
    )
    return subject, body, html


def portal_form_completed_staff(
    *,
    firm_name: str,
    contact_name: str,
    form_name: str,
    matter_label: str,
) -> tuple[str, str, str]:
    subject = f"Portal form completed — {form_name}"
    body = "\n".join(
        [
            f"{contact_name} completed a portal form.",
            "",
            f"Form: {form_name}",
            f"Matter: {matter_label}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(
            title=f"{contact_name} completed a portal form",
            lines=[f"Form: {form_name}", f"Matter: {matter_label}"],
        ),
    )
    return subject, body, html


def portal_form_sent(
    *,
    firm_name: str,
    contact_name: str,
    form_name: str,
    matter_label: str,
    portal_url: str,
) -> tuple[str, str, str]:
    subject = f"Form to complete — {matter_label}"
    cta_label = "Complete form"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Please complete the form: {form_name}",
            f"Matter: {matter_label}",
            "",
            f"{cta_label}: {portal_url}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            f"<p>Please complete the form: <strong>{_escape_html(form_name)}</strong></p>"
            f'<p style="margin:0 0 4px;color:#64748b;">Matter: {_escape_html(matter_label)}</p>'
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
        ),
    )
    return subject, body, html


def portal_quote_sent(
    *,
    firm_name: str,
    contact_name: str,
    quote_filename: str,
    matter_label: str,
    portal_url: str,
) -> tuple[str, str, str]:
    subject = f"Quote — {matter_label}"
    cta_label = "View your quote"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Please review your quote for {matter_label}:",
            quote_filename,
            "",
            f"{cta_label}: {portal_url}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            f"<p>Please review your quote for <strong>{_escape_html(matter_label)}</strong>:</p>"
            f'<p style="margin:0 0 4px;color:#64748b;">{_escape_html(quote_filename)}</p>'
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
        ),
    )
    return subject, body, html


def portal_quote_accepted(
    *,
    firm_name: str,
    contact_name: str,
    quote_filename: str,
) -> tuple[str, str, str]:
    subject = f"Quote accepted: {quote_filename}"
    body = "\n".join(
        [
            f"{contact_name} accepted the quote via Canary Portal.",
            "",
            f"File: {quote_filename}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(
            title=f"{contact_name} accepted the quote via Canary Portal",
            lines=[f"File: {quote_filename}"],
        ),
    )
    return subject, body, html


def portal_quote_declined(
    *,
    firm_name: str,
    contact_name: str,
    quote_filename: str,
    decline_reason: str,
) -> tuple[str, str, str]:
    subject = f"Quote declined: {quote_filename}"
    lines = [f"{contact_name} declined the quote via Canary Portal.", "", f"File: {quote_filename}"]
    info_lines = [f"File: {quote_filename}"]
    if decline_reason.strip():
        lines.extend(["", f"Reason: {decline_reason.strip()}"])
        info_lines.append(f"Reason: {decline_reason.strip()}")
    body = "\n".join(lines + ["", f"— {_firm_line(firm_name)}"])
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(
            title=f"{contact_name} declined the quote via Canary Portal",
            lines=info_lines,
        ),
    )
    return subject, body, html


def portal_login_otp(
    *,
    firm_name: str,
    contact_name: str,
    portal_url: str,
    otp_code: str,
) -> tuple[str, str, str]:
    subject = f"Your Canary Portal sign-in code — {_firm_line(firm_name)}"
    cta_label = "Sign in to portal"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Your sign-in code is: {otp_code}",
            "",
            f"{cta_label}: {portal_url}",
            "",
            "This code is valid for 15 minutes.",
            "",
            "If you did not request this code, you can ignore this e-mail.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=(
            f"<p>Dear {_escape_html(contact_name)},</p>"
            f"{_html_highlight_code('Your sign-in code', otp_code)}"
            f"{_html_cta_button(portal_url, cta_label)}"
            f"{_html_fallback_link(portal_url)}"
            '<p style="font-size:13px;color:#64748b;margin:0;">'
            "This code is valid for 15 minutes. If you did not request this code, you can ignore this e-mail."
            "</p>"
        ),
    )
    return subject, body, html


def docusign_sign_requested(
    *,
    firm_name: str,
    recipient_name: str,
    document_name: str,
    matter_label: str,
    sign_url: str,
) -> tuple[str, str, str]:
    subject = f"Please sign — {matter_label}"
    body = "\n".join(
        [
            f"Dear {recipient_name},",
            "",
            f"You have a document to sign for matter {matter_label}:",
            document_name,
            "",
            f"Sign here: {sign_url}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {recipient_name},",
            f"You have a document to sign for matter {matter_label}: {document_name}",
            f'Sign here: <a href="{_escape_html(sign_url)}">{_escape_html(sign_url)}</a>',
        ],
    )
    return subject, body, html


def docusign_sign_sent_staff(
    *,
    firm_name: str,
    staff_name: str,
    document_name: str,
    sender_name: str,
) -> tuple[str, str, str]:
    subject = f"DocuSign sent: {document_name}"
    body = "\n".join(
        [
            f"{sender_name} sent a document for signature via DocuSign:",
            "",
            document_name,
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[f"{sender_name} sent {document_name} for signature via DocuSign."],
    )
    return subject, body, html


def docusign_sign_completed_staff(
    *,
    firm_name: str,
    staff_name: str,
    document_name: str,
) -> tuple[str, str, str]:
    subject = f"DocuSign completed: {document_name}"
    body = "\n".join(
        [
            "A DocuSign envelope has been completed:",
            "",
            document_name,
            "",
            "The signed document has been filed on the matter in Canary.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"The DocuSign envelope for {document_name} is complete.",
            "The signed document has been filed on the matter in Canary.",
        ],
    )
    return subject, body, html


def _matter_lines(*, case_number: str, matter_label: str) -> list[str]:
    lines: list[str] = []
    if case_number:
        lines.append(f"Matter: {case_number}")
    if matter_label and matter_label != case_number:
        lines.append(matter_label)
    return lines


def _optional_comment_lines(comment: str) -> list[str]:
    text = (comment or "").strip()
    if not text:
        return []
    return ["", "Comment:", text]


def anticipated_payment_approved(
    *,
    firm_name: str,
    staff_name: str,
    decider_name: str,
    case_number: str,
    matter_label: str,
    description: str,
    amount_gbp: str,
    reference: str,
) -> tuple[str, str, str]:
    ref = (reference or "").strip()
    subject = f"Anticipated payment accepted — {case_number or matter_label or 'matter'}"
    body_lines = [
        f"Hello {staff_name},",
        "",
        f"{decider_name} has accepted your anticipated payment in Canary.",
        "",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        body_lines.append(f"Reference: {ref}")
    body_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    body_lines.append("")
    body_lines.append(f"— {_firm_line(firm_name)}")
    body = "\n".join(body_lines)
    html_lines = [
        f"{decider_name} has accepted your anticipated payment.",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        html_lines.append(f"Reference: {ref}")
    html_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(title=f"Hello {staff_name}", lines=html_lines),
    )
    return subject, body, html


def anticipated_payment_rejected(
    *,
    firm_name: str,
    staff_name: str,
    decider_name: str,
    case_number: str,
    matter_label: str,
    description: str,
    amount_gbp: str,
    reference: str,
    comment: str,
) -> tuple[str, str, str]:
    ref = (reference or "").strip()
    subject = f"Anticipated payment not accepted — {case_number or matter_label or 'matter'}"
    body_lines = [
        f"Hello {staff_name},",
        "",
        f"{decider_name} has not accepted your anticipated payment in Canary.",
        "",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        body_lines.append(f"Reference: {ref}")
    body_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    body_lines.extend(_optional_comment_lines(comment))
    body_lines.append("")
    body_lines.append(f"— {_firm_line(firm_name)}")
    body = "\n".join(body_lines)
    html_lines = [
        f"{decider_name} has not accepted your anticipated payment.",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        html_lines.append(f"Reference: {ref}")
    html_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    comment_text = (comment or "").strip()
    if comment_text:
        html_lines.append(f"Comment: {comment_text}")
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(title=f"Hello {staff_name}", lines=html_lines),
    )
    return subject, body, html


def anticipated_payment_amended(
    *,
    firm_name: str,
    staff_name: str,
    editor_name: str,
    poster_name: str,
    case_number: str,
    matter_label: str,
    description: str,
    amount_gbp: str,
    reference: str,
) -> tuple[str, str, str]:
    ref = (reference or "").strip()
    subject = f"Anticipated payment amended — {case_number or matter_label or 'matter'}"
    body_lines = [
        f"Hello {staff_name},",
        "",
        f"{editor_name} has amended an anticipated payment on your matter in Canary.",
        f"It was originally posted by {poster_name}.",
        "",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        body_lines.append(f"Reference: {ref}")
    body_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    body_lines.append("")
    body_lines.append(f"— {_firm_line(firm_name)}")
    body = "\n".join(body_lines)
    html_lines = [
        f"{editor_name} has amended an anticipated payment originally posted by {poster_name}.",
        description,
        f"Amount: {amount_gbp}",
    ]
    if ref:
        html_lines.append(f"Reference: {ref}")
    html_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(title=f"Hello {staff_name}", lines=html_lines),
    )
    return subject, body, html


def invoice_approved_staff(
    *,
    firm_name: str,
    staff_name: str,
    decider_name: str,
    case_number: str,
    matter_label: str,
    invoice_number: str,
    amount_gbp: str,
) -> tuple[str, str, str]:
    subject = f"Invoice {invoice_number} approved"
    body_lines = [
        f"Hello {staff_name},",
        "",
        f"{decider_name} has approved invoice {invoice_number} in Canary.",
        f"Total: {amount_gbp}",
    ]
    body_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    body_lines.append("")
    body_lines.append(f"— {_firm_line(firm_name)}")
    body = "\n".join(body_lines)
    html_lines = [
        f"{decider_name} has approved invoice {invoice_number}.",
        f"Total: {amount_gbp}",
    ]
    html_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(title=f"Hello {staff_name}", lines=html_lines),
    )
    return subject, body, html


def invoice_rejected_staff(
    *,
    firm_name: str,
    staff_name: str,
    decider_name: str,
    case_number: str,
    matter_label: str,
    invoice_number: str,
    amount_gbp: str,
    comment: str,
) -> tuple[str, str, str]:
    subject = f"Invoice {invoice_number} not approved"
    body_lines = [
        f"Hello {staff_name},",
        "",
        f"{decider_name} has not approved invoice {invoice_number} in Canary.",
        f"Total: {amount_gbp}",
    ]
    body_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    body_lines.extend(_optional_comment_lines(comment))
    body_lines.append("")
    body_lines.append(f"— {_firm_line(firm_name)}")
    body = "\n".join(body_lines)
    html_lines = [
        f"{decider_name} has not approved invoice {invoice_number}.",
        f"Total: {amount_gbp}",
    ]
    html_lines.extend(_matter_lines(case_number=case_number, matter_label=matter_label))
    comment_text = (comment or "").strip()
    if comment_text:
        html_lines.append(f"Comment: {comment_text}")
    html = _html_email_shell(
        firm_name=firm_name,
        inner_html=_html_info_block(title=f"Hello {staff_name}", lines=html_lines),
    )
    return subject, body, html
