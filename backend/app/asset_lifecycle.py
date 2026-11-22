"""Transactional retirement of firm/user assets; bytes survive rollback and lost ACKs."""
from sqlalchemy import select
from app.document_durability import retain_document, lock_document
from app.models import File


def retire_asset(db, owner, field, *, root):
    # Serialize replacements against the current pointer, not a stale identity-map copy.
    with db.no_autoflush:
        owner = db.scalar(select(type(owner)).where(type(owner).id == owner.id)
                          .with_for_update().execution_options(populate_existing=True))
    identity = getattr(owner, field)
    if identity is None:
        return
    row = db.get(File, identity)
    if row is not None:
        row = lock_document(db, row)
        retain_document(db, row, root=root, kind='deleted')
    setattr(owner, field, None)
    db.flush()
    if row is not None:
        db.delete(row)
        db.flush()
    # Caller publishes the replacement pointer and audit in its own transaction.
    # No unlink here: even a definitive rollback must keep the original usable.
