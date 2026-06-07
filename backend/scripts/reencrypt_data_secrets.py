#!/usr/bin/env python3
"""Re-encrypt stored secrets from the legacy JWT_SECRET-derived key to DATA_ENCRYPTION_KEY.

Requires both JWT_SECRET (legacy decrypt) and DATA_ENCRYPTION_KEY (new encrypt) in the environment.

Run inside the backend container:
  python scripts/reencrypt_data_secrets.py
  python scripts/reencrypt_data_secrets.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.email_crypt import decrypt_password, encrypt_password, needs_reencryption, uses_legacy_encryption_key
from app.models import ContactPortalAccess, EmailIntegrationSettings, SmtpNotificationSettings, User


def _maybe_reencrypt(value: str | None, *, dry_run: bool) -> tuple[str | None, bool]:
    enc = (value or "").strip()
    if not enc:
        return value, False
    if not needs_reencryption(enc):
        return value, False
    plain = decrypt_password(enc)
    if dry_run:
        return value, True
    return encrypt_password(plain), True


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-encrypt Fernet secrets under DATA_ENCRYPTION_KEY.")
    parser.add_argument("--dry-run", action="store_true", help="Report rows that would change without writing.")
    args = parser.parse_args()

    if uses_legacy_encryption_key():
        print("ERROR: DATA_ENCRYPTION_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    changed = 0
    try:
        for user in db.scalars(select(User).where(User.caldav_password_enc.is_not(None))).all():
            new_val, did = _maybe_reencrypt(user.caldav_password_enc, dry_run=args.dry_run)
            if did:
                changed += 1
                print(f"user {user.id} caldav_password_enc")
                if not args.dry_run:
                    user.caldav_password_enc = new_val

        for row in db.scalars(select(ContactPortalAccess).where(ContactPortalAccess.code_enc.is_not(None))).all():
            new_val, did = _maybe_reencrypt(row.code_enc, dry_run=args.dry_run)
            if did:
                changed += 1
                print(f"contact_portal_access {row.id} code_enc")
                if not args.dry_run:
                    row.code_enc = new_val

        email_row = db.get(EmailIntegrationSettings, 1)
        if email_row and email_row.graph_client_secret_enc:
            new_val, did = _maybe_reencrypt(email_row.graph_client_secret_enc, dry_run=args.dry_run)
            if did:
                changed += 1
                print("email_integration_settings graph_client_secret_enc")
                if not args.dry_run:
                    email_row.graph_client_secret_enc = new_val

        smtp_row = db.get(SmtpNotificationSettings, 1)
        if smtp_row and smtp_row.password_enc:
            new_val, did = _maybe_reencrypt(smtp_row.password_enc, dry_run=args.dry_run)
            if did:
                changed += 1
                print("smtp_notification_settings password_enc")
                if not args.dry_run:
                    smtp_row.password_enc = new_val

        if args.dry_run:
            print(f"Dry run: {changed} value(s) would be re-encrypted.")
        else:
            db.commit()
            print(f"Re-encrypted {changed} value(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
