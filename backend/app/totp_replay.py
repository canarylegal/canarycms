"""Consume an authenticator time step atomically in the caller's transaction."""
import hashlib
import time
import pyotp
from sqlalchemy.orm import Session
from app.models import TotpReplayState


def consume_totp(db: Session, *, secret: str, code: str) -> bool:
    try:
        totp = pyotp.TOTP(secret)
        current = int(time.time()) // totp.interval
        matches = [step for step in range(max(0, current - 1), current + 2)
                   if pyotp.utils.strings_equal(totp.generate_otp(step), str(code))]
    except Exception:
        # Invalid configured secrets/codes must fail closed, as the previous verifier did.
        return False
    if not matches:
        return False
    step = max(matches)
    # The high-entropy authenticator secret is never stored here; rotation gets a new identity.
    factor_id = hashlib.sha256(secret.upper().encode("ascii")).hexdigest()
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(TotpReplayState).values(factor_id=factor_id, last_step=step)
    stmt = stmt.on_conflict_do_update(index_elements=[TotpReplayState.factor_id],
        set_={"last_step": step}, where=TotpReplayState.last_step < min(matches))
    return db.execute(stmt.returning(TotpReplayState.factor_id)).scalar_one_or_none() is not None
