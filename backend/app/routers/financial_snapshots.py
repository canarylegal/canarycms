"""Archive history and byte-exact downloads. Existing UI routes remain unchanged."""

import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import get_current_user
from app.bank_integrity import require_banking
from app.download_headers import attachment_content_disposition_headers
from app.financial_report_snapshots import authorized_artifact, download_snapshot
from app.models import FinancialReportSnapshot, User

router = APIRouter(
    prefix="/reports/approved-snapshots", tags=["approved-financial-reports"]
)


@router.get("")
def history(
    source_kind: Literal["firm", "bank"],
    source_id: uuid.UUID,
    before_version: int | None = Query(None, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_banking(user, db)
    query = select(FinancialReportSnapshot).where(
        FinancialReportSnapshot.source_kind == source_kind,
        FinancialReportSnapshot.source_id == source_id,
    )
    if before_version is not None:
        query = query.where(FinancialReportSnapshot.version < before_version)
    rows = list(
        db.scalars(
            query.order_by(FinancialReportSnapshot.version.desc()).limit(limit + 1)
        )
    )
    result = []
    for row in rows[:limit]:
        manifest = authorized_artifact(db, row, user)
        result.append(
            {
                k: manifest[k]
                for k in (
                    "snapshot_id",
                    "source_kind",
                    "source_id",
                    "version",
                    "previous_id",
                    "approved_at",
                    "approved_by_user_id",
                    "created_at",
                    "period_end_date",
                    "revision_reason",
                    "build_commit",
                )
            }
            | dict(integrity="verified", sha256=row.archive_sha256)
        )
    return dict(
        items=result,
        next_before_version=rows[limit - 1].version if len(rows) > limit else None,
        legacy_not_backfilled=True,
    )


@router.get("/{snapshot_id}/download")
def download(
    snapshot_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_banking(user, db)
    row = db.get(FinancialReportSnapshot, snapshot_id)
    if row is None:
        raise HTTPException(404, "Approved report snapshot not found")
    content, name, media = download_snapshot(db, row, user)
    return Response(
        content,
        media_type=media,
        headers={
            **attachment_content_disposition_headers(name),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": row.archive_sha256,
            "X-Canary-Snapshot-Version": str(row.version),
        },
    )
