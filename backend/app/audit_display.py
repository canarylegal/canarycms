from __future__ import annotations

from typing import Any

from app.ledger_audit import format_amount_pence, format_ledger_directions


def parse_audit_meta(meta_json: str | None) -> dict[str, Any] | None:
    if not meta_json:
        return None
    import json

    try:
        raw = json.loads(meta_json)
    except Exception:
        return {"_raw": meta_json}
    return raw if isinstance(raw, dict) else {"_value": raw}


def extract_case_id(
    *,
    entity_type: str | None,
    entity_id: str | None,
    meta: dict[str, Any] | None,
) -> str | None:
    if meta:
        cid = meta.get("case_id")
        if cid:
            return str(cid)
    if entity_type == "case" and entity_id:
        return str(entity_id)
    return None


def _s(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _quote(value: Any) -> str:
    text = _s(value)
    return f'"{text}"' if text else ""


def format_audit_summary(
    *,
    action: str,
    entity_type: str | None,
    entity_id: str | None,
    meta: dict[str, Any] | None,
) -> str:
    m = meta or {}

    if action == "auth.login":
        return "Signed in"
    if action == "auth.login.passkey":
        return "Signed in with passkey"
    if action == "auth.password.reset":
        return "Completed password reset"
    if action == "auth.password.reset_email":
        return "Requested password reset e-mail"
    if action == "auth.password.change":
        return "Changed password"
    if action == "auth.2fa.enable":
        return "Enabled two-factor authentication"
    if action == "auth.2fa.disable_self":
        return "Disabled two-factor authentication"
    if action == "auth.2fa.cancel_setup":
        return "Cancelled two-factor authentication setup"
    if action == "auth.webauthn.register":
        return "Registered a passkey"
    if action == "auth.webauthn.delete":
        return "Removed a passkey"

    if action == "case.create":
        ref = _s(m.get("case_number")) or _s(entity_id)
        title = _s(m.get("matter_description"))
        client = _s(m.get("client_name"))
        parts = [f"Created matter {ref}"]
        if client:
            parts.append(f"({client})")
        if title:
            parts.append(f"— {title}")
        return " ".join(parts)

    if action == "case.update":
        fields = [k for k in m.keys() if k not in {"case_id"}]
        if fields:
            return f"Updated matter settings ({', '.join(fields)})"
        return "Updated matter settings"

    if action == "case.file.upload":
        fn = _quote(m.get("filename"))
        folder = _s(m.get("folder"))
        if folder:
            return f"Uploaded file {fn} to {folder}"
        return f"Uploaded file {fn}"

    if action == "case.file.rename":
        old = _quote(m.get("old_filename") or m.get("filename"))
        new = _quote(m.get("new_filename") or m.get("filename"))
        if old and new and old != new:
            return f"Renamed file {old} to {new}"
        return f"Renamed file to {new}" if new else "Renamed a file"

    if action == "case.file.delete":
        fn = _quote(m.get("filename"))
        return f"Deleted file {fn}" if fn else "Deleted a file"

    if action == "case.file.move":
        fn = _quote(m.get("filename"))
        old_folder = _s(m.get("old_folder_path"))
        new_folder = _s(m.get("new_folder_path") or m.get("folder_path"))
        if fn and new_folder:
            if old_folder and old_folder != new_folder:
                return f"Moved file {fn} from {old_folder} to {new_folder}"
            return f"Moved file {fn} to {new_folder}"
        if new_folder:
            return f"Moved a file to {new_folder}"
        return "Moved a file"

    if action == "case.file.comment.update":
        old = _quote(m.get("old_filename"))
        new = _quote(m.get("new_filename") or m.get("filename"))
        if old and new and old != new:
            return f"Updated comment {old} → {new}"
        return f"Updated comment {new}" if new else "Updated a comment"

    if action == "case.folder.create":
        name = _quote(m.get("folder_name"))
        path = _s(m.get("folder_path"))
        if name and path:
            return f"Created folder {name} at {path}"
        return f"Created folder {name}" if name else "Created a folder"

    if action == "case.folder.rename":
        old = _s(m.get("old_folder_path"))
        new = _s(m.get("new_folder_path"))
        if old and new:
            return f"Renamed folder {old} to {new}"
        return "Renamed a folder"

    if action == "case.folder.delete":
        path = _s(m.get("folder_path"))
        count = m.get("deleted_count")
        if path and count is not None:
            return f"Deleted folder {path} ({count} item(s))"
        if path:
            return f"Deleted folder {path}"
        return "Deleted a folder"

    if action == "case.file.compose_quote":
        return "Created a quote document"
    if action == "case.file.compose_office":
        return "Created a document from a precedent"
    if action == "case.file.compose_publish":
        fn = _quote(m.get("filename"))
        return f"Published composed document {fn}" if fn else "Published composed document"
    if action == "case.file.compose_discard":
        fn = _quote(m.get("filename"))
        return f"Discarded composed document {fn}" if fn else "Discarded composed document"

    if action == "case.task.create":
        title = _quote(m.get("title"))
        return f"Created task {title}" if title else "Created a task"
    if action == "case.task.update":
        title = _quote(m.get("title"))
        return f"Updated task {title}" if title else "Updated a task"
    if action == "case.task.delete":
        title = _quote(m.get("title"))
        return f"Deleted task {title}" if title else "Deleted a task"

    if action == "case.note.create":
        return "Added a case note"
    if action == "case.note.update":
        return "Updated a case note"
    if action == "case.note.delete":
        return "Deleted a case note"

    if action == "ledger.post":
        amt = format_ledger_directions(m)
        desc = _quote(m.get("description"))
        inv = _s(m.get("invoice_number"))
        pending = " (pending approval)" if m.get("is_approved") is False else ""
        parts = [f"Posted {amt}{pending}"]
        if inv:
            parts.append(f"for {inv}")
        if desc:
            parts.append(f"— {desc.strip('\"')}")
        return " ".join(parts)

    if action == "ledger.approve":
        amt = format_ledger_directions(m)
        desc = _quote(m.get("description"))
        if desc:
            return f"Approved ledger posting {amt} — {desc.strip('\"')}"
        return f"Approved ledger posting {amt}"

    if action == "invoice.create":
        inv = _s(m.get("invoice_number"))
        amt = format_amount_pence(m.get("amount_pence"))
        return f"Created invoice {inv} ({amt})" if inv else f"Created invoice ({amt})"

    if action == "invoice.approve":
        inv = _s(m.get("invoice_number"))
        amt = format_amount_pence(m.get("amount_pence"))
        return f"Approved invoice {inv} ({amt})" if inv else f"Approved invoice ({amt})"

    if action == "invoice.void":
        inv = _s(m.get("invoice_number"))
        amt = format_amount_pence(m.get("amount_pence"))
        if m.get("was_pending"):
            return f"Voided pending invoice {inv} ({amt})" if inv else f"Voided pending invoice ({amt})"
        return f"Voided invoice {inv} ({amt})" if inv else f"Voided invoice ({amt})"

    if action == "reconciliation.create":
        period = _s(m.get("period_end_date"))
        diff = format_amount_pence(m.get("difference_pence"))
        return f"Created client account reconciliation for {period} (difference {diff})"

    if action == "reconciliation.update":
        period = _s(m.get("period_end_date"))
        diff = format_amount_pence(m.get("difference_pence"))
        return f"Updated client account reconciliation for {period} (difference {diff})"

    if action == "reconciliation.approve":
        period = _s(m.get("period_end_date"))
        diff = format_amount_pence(m.get("difference_pence"))
        return f"Approved client account reconciliation for {period} (difference {diff})"

    if action == "portal.file.upload":
        fn = _quote(m.get("filename"))
        return f"Portal upload: {fn}" if fn else "Portal file upload"
    if action == "portal.file.download":
        fn = _quote(m.get("filename"))
        return f"Portal download: {fn}" if fn else "Portal file download"
    if action == "portal.file.open":
        fn = _quote(m.get("filename"))
        return f"Portal opened file {fn}" if fn else "Portal opened a file"
    if action == "portal.auth.success":
        return "Portal sign-in succeeded"

    if action == "admin.user.create":
        return f"Created user {_quote(m.get('email') or m.get('initials'))}"
    if action == "admin.user.update":
        return f"Updated user {_quote(m.get('initials') or entity_id)}"
    if action == "admin.user.set_password":
        return "Set a user password"
    if action == "admin.user.disable_2fa":
        return "Disabled a user's two-factor authentication"

    if action.startswith("firm_settings."):
        return action.replace("firm_settings.", "Firm settings: ").replace("_", " ")
    if action.startswith("contact.portal."):
        return action.replace("contact.portal.", "Portal access: ").replace("_", " ")

    if entity_type and entity_id:
        return f"{action} ({entity_type} {entity_id})"
    return action.replace(".", " · ").replace("_", " ")
