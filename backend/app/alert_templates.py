"""Plain-text templates for automated internal and external alerts."""

from __future__ import annotations


def _firm_line(firm_name: str) -> str:
    name = (firm_name or "").strip()
    return name or "Your firm"


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
) -> tuple[str, str]:
    subject = f"Portal upload: {filename}"
    body = "\n".join(
        [
            f"{contact_name} uploaded a file via the client portal.",
            "",
            f"Area: {area_label}",
            f"File: {filename}",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    return subject, body


def portal_contact_access_granted(
    *,
    firm_name: str,
    contact_name: str,
    portal_url: str,
    access_code: str,
) -> tuple[str, str]:
    subject = f"Client portal access — {_firm_line(firm_name)}"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            "You can access your documents using our secure client portal.",
            "",
            f"Portal: {portal_url}",
            f"Access code: {access_code}",
            "",
            "Keep this code confidential. Contact us if you need a new code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    return subject, body


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
) -> tuple[str, str]:
    subject = f"Documents shared with you — {_firm_line(firm_name)}"
    body = "\n".join(
        [
            f"Dear {contact_name},",
            "",
            f"Documents have been shared with you: {area_label}",
            "",
            f"Sign in at {portal_url} with your personal access code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    return subject, body


def portal_contact_files_added(
    *,
    firm_name: str,
    contact_name: str,
    area_label: str,
    filenames: list[str],
    portal_url: str,
) -> tuple[str, str]:
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
            f"View them at {portal_url} using your access code.",
            "",
            f"— {_firm_line(firm_name)}",
        ]
    )
    return subject, "\n".join(lines)
