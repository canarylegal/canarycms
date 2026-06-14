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
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"{contact_name} uploaded a file via Canary Portal.",
            f"Area: {area_label}",
            f"File: {filename}",
        ],
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
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            "You can access your documents using Canary Portal.",
            "",
            f"Portal: {portal_url}",
            f"Access code: {access_code}",
            "",
            "Keep this code confidential. Contact us if you need a new code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {contact_name},",
            "You can access your documents using Canary Portal.",
            f"Portal: {portal_url}",
            f"Access code: {access_code}",
            "Keep this code confidential. Contact us if you need a new code.",
        ],
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
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Documents have been shared with you: {area_label}",
            "",
            f"Sign in at {portal_url} with your personal access code or e-mail sign-in code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {contact_name},",
            f"Documents have been shared with you: {area_label}",
            f"Sign in at {portal_url} with your access code or e-mail sign-in code.",
        ],
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
            f"View them at {portal_url} using your access code or e-mail sign-in code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    body = "\n".join(lines)
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {contact_name},",
            f"New file(s) are available in {area_label}:",
            f"View them at {portal_url}.",
        ],
        bullets=filenames,
    )
    return subject, body, html


def portal_quote_sent(
    *,
    firm_name: str,
    contact_name: str,
    quote_filename: str,
    portal_url: str,
) -> tuple[str, str, str]:
    subject = f"Quote from {_firm_line(firm_name)}"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Please review your quote: {quote_filename}",
            "",
            f"View and respond at: {portal_url}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {contact_name},",
            f"Please review your quote: {quote_filename}",
            f"View and respond at: {portal_url}",
        ],
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
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[f"{contact_name} accepted the quote via Canary Portal.", f"File: {quote_filename}"],
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
    if decline_reason.strip():
        lines.extend(["", f"Reason: {decline_reason.strip()}"])
    body = "\n".join(lines + ["", f"— {_firm_line(firm_name)}"])
    html_parts = [f"{contact_name} declined the quote via Canary Portal.", f"File: {quote_filename}"]
    if decline_reason.strip():
        html_parts.append(f"Reason: {decline_reason.strip()}")
    html = _html_email(firm_name=firm_name, paragraphs=html_parts)
    return subject, body, html


def portal_login_otp(
    *,
    firm_name: str,
    contact_name: str,
    portal_url: str,
    otp_code: str,
) -> tuple[str, str, str]:
    subject = f"Your Canary Portal sign-in code — {_firm_line(firm_name)}"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Your sign-in code is: {otp_code}",
            "",
            f"Enter this code at {portal_url} (valid for 15 minutes).",
            "",
            "If you did not request this code, you can ignore this e-mail.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    html = _html_email(
        firm_name=firm_name,
        paragraphs=[
            f"Dear {contact_name},",
            f"Your sign-in code is: {otp_code}",
            f"Enter this code at {portal_url} (valid for 15 minutes).",
            "If you did not request this code, you can ignore this e-mail.",
        ],
    )
    return subject, body, html
