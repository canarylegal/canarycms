"""Send sample portal alert e-mails via the configured firm transport.

Usage (inside backend container or with DB env set):
  python -m scripts.send_portal_email_samples colin@example.com
"""

from __future__ import annotations

import sys
import uuid

from app.alert_templates import (
    portal_contact_access_granted,
    portal_contact_files_added,
    portal_contact_folder_granted,
    portal_form_completed_staff,
    portal_form_sent,
    portal_login_otp,
    portal_quote_accepted,
    portal_quote_declined,
    portal_quote_sent,
    portal_staff_upload,
)
from app.db import SessionLocal
from app.firm_email_service import FirmEmailMessage, firm_email_status, send_firm_email


def main() -> int:
    to_email = (sys.argv[1] if len(sys.argv) > 1 else "colin@canarylegalsoftware.co.uk").strip()
    firm = "Ashbourne & Finch"
    portal_url = "https://dev.canarylegalsoftware.co.uk/portal"
    matter_label_client = "Purchase of 12 High Street"
    matter_label_staff = "000002 — Purchase of 12 High Street"
    matter_url = f"https://dev.canarylegalsoftware.co.uk/case/{uuid.UUID('00000000-0000-4000-8000-000000000002')}"
    contact = "Alex Brown"

    samples: list[tuple[str, str, str]] = []

    s, b, h = portal_contact_access_granted(
        firm_name=firm,
        contact_name=contact,
        portal_url=portal_url,
        access_code="CANARY-DEMO-42",
    )
    samples.append((s, b, h))

    s, b, h = portal_contact_folder_granted(
        firm_name=firm,
        contact_name=contact,
        area_label="Shared with you",
        portal_url=portal_url,
    )
    samples.append((s, b, h))

    s, b, h = portal_contact_files_added(
        firm_name=firm,
        contact_name=contact,
        area_label="Shared with you",
        filenames=["Letter of engagement.pdf", "ID checklist.pdf"],
        portal_url=portal_url,
    )
    samples.append((s, b, h))

    s, b, h = portal_form_sent(
        firm_name=firm,
        contact_name=contact,
        form_name="Client details",
        matter_label=matter_label_client,
        portal_url=f"{portal_url}/f/{uuid.uuid4()}",
        access_code="CANARY-DEMO-42",
    )
    samples.append((s, b, h))

    s, b, h = portal_quote_sent(
        firm_name=firm,
        contact_name=contact,
        quote_filename="Quote — All clients.pdf",
        matter_label=matter_label_client,
        portal_url=f"{portal_url}/q/{uuid.uuid4()}",
        access_code="CANARY-DEMO-42",
    )
    samples.append((s, b, h))

    s, b, h = portal_login_otp(
        firm_name=firm,
        contact_name=contact,
        portal_url=portal_url,
        otp_code="847291",
    )
    samples.append((s, b, h))

    s, b, h = portal_staff_upload(
        firm_name=firm,
        contact_name=contact,
        area_label="Shared with you",
        filename="Bank statement.pdf",
        matter_label=matter_label_staff,
        matter_url=matter_url,
    )
    samples.append((s, b, h))

    s, b, h = portal_form_completed_staff(
        firm_name=firm,
        contact_name=contact,
        form_name="Client details",
        matter_label=matter_label_staff,
        matter_url=matter_url,
    )
    samples.append((s, b, h))

    s, b, h = portal_quote_accepted(
        firm_name=firm,
        contact_name=contact,
        quote_filename="Quote — All clients.pdf",
        matter_label=matter_label_staff,
        matter_url=matter_url,
    )
    samples.append((s, b, h))

    s, b, h = portal_quote_declined(
        firm_name=firm,
        contact_name=contact,
        quote_filename="Quote — All clients.pdf",
        decline_reason="Looking at other options for now.",
        matter_label=matter_label_staff,
        matter_url=matter_url,
    )
    samples.append((s, b, h))

    db = SessionLocal()
    try:
        status = firm_email_status(db)
        print("alert status:", status)
        if not status.get("effective_transport"):
            print("ERROR: alert transport not configured; aborting", file=sys.stderr)
            return 1
        for subject, body, html in samples:
            tagged = f"[Example] {subject}"
            transport = send_firm_email(
                db,
                FirmEmailMessage(to_email=to_email, subject=tagged, body_text=body, body_html=html),
            )
            print(f"sent via {transport}: {tagged}")
        db.commit()
    finally:
        db.close()
    print(f"done: {len(samples)} messages to {to_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
