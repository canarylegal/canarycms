"""Admin: file storage usage reporting and optional quota limit."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import require_admin
from app.file_storage import FILES_ROOT
from app.models import FirmSettings, User
from app.schemas import (
    AdminStorageCategoryOut,
    AdminStorageDeploymentComponentOut,
    AdminStorageOut,
    AdminStorageSettingsPatch,
)
from app.storage_usage import aggregate_storage_by_category, detect_files_root_disk, measure_deployment_storage, total_tracked_bytes

router = APIRouter(prefix="/admin/storage", tags=["admin-storage"])


def _settings_row(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=AdminStorageOut)
def read_storage(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminStorageOut:
    categories = aggregate_storage_by_category(db)
    tracked_total = total_tracked_bytes(categories)
    snapshot = measure_deployment_storage(db)
    settings = _settings_row(db)
    disk_detected, disk_total, disk_used, disk_free = detect_files_root_disk()
    return AdminStorageOut(
        tracked_total_bytes=tracked_total,
        files_on_disk_bytes=snapshot.files_on_disk_bytes,
        compose_mount_bytes=snapshot.compose_mount_bytes,
        application_checkout_bytes=snapshot.application_checkout_bytes,
        database_bytes=snapshot.database_on_disk_bytes,
        database_logical_bytes=snapshot.database_logical_bytes,
        calendars_bytes=snapshot.calendars_bytes,
        deployment_total_bytes=snapshot.deployment_total_bytes,
        docker_detected=snapshot.docker_detected,
        docker_images_bytes=snapshot.docker_images_bytes,
        docker_container_writable_bytes=snapshot.docker_container_writable_bytes,
        docker_dangling_images_bytes=snapshot.docker_dangling_images_bytes,
        docker_build_cache_bytes=snapshot.docker_build_cache_bytes,
        deployment_active_bytes=snapshot.deployment_active_bytes,
        deployment_artifacts_bytes=snapshot.deployment_artifacts_bytes,
        measurement_note=snapshot.measurement_note,
        deployment_components=[
            AdminStorageDeploymentComponentOut(
                key=c.key,
                label=c.label,
                bytes_used=c.bytes_used,
                detected=c.detected,
            )
            for c in snapshot.components
            if c.detected
        ],
        categories=[
            AdminStorageCategoryOut(
                category=c.category,
                label=c.label,
                bytes_used=c.bytes_used,
                file_count=c.file_count,
            )
            for c in categories
        ],
        storage_limit_bytes=settings.storage_limit_bytes,
        files_root=str(FILES_ROOT),
        host_disk_detected=disk_detected,
        host_disk_total_bytes=disk_total,
        host_disk_used_bytes=disk_used,
        host_disk_free_bytes=disk_free,
    )


@router.patch("/settings", response_model=AdminStorageOut)
def patch_storage_settings(
    payload: AdminStorageSettingsPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminStorageOut:
    if not payload.model_fields_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")

    row = _settings_row(db)
    if "storage_limit_bytes" in payload.model_fields_set:
        limit = payload.storage_limit_bytes
        if limit is not None and limit < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Storage limit must be at least 1 byte.")
        row.storage_limit_bytes = limit
        row.updated_at = datetime.utcnow()
        log_event(
            db,
            actor_user_id=admin.id,
            action="storage_settings.update",
            entity_type="firm_settings",
            entity_id="1",
            meta={"storage_limit_bytes": limit},
        )
    db.commit()
    return read_storage(_admin=admin, db=db)


@router.get('/upload-scanning')
def upload_scan_status(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from sqlalchemy import select, func
    from app.models import File
    from app.upload_scanning import mode, scanner_version, ScanFailure
    import os
    counts = dict(db.execute(select(File.scan_state, func.count()).group_by(File.scan_state)).all())
    version = None; scanner = 'disabled'
    if mode() == 'required':
        try:
            version = scanner_version(); scanner = 'ready'
        except ScanFailure:
            scanner = 'unavailable_or_stale'
    return {'mode': mode(), 'scanner': scanner, 'version': version, 'worker_enabled': os.getenv('CANARY_UPLOAD_SCAN_WORKER_ENABLED', '0') == '1',
            'counts': counts, 'configuration_source': '.env'}


@router.get('/upload-scanning/quarantine')
def list_quarantine(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models import File
    rows = db.scalars(select(File).where(File.scan_state.in_(['pending', 'error', 'blocked']))
                      .order_by(File.created_at.desc()).limit(200)).all()
    return [{'id': str(r.id), 'case_id': str(r.case_id), 'filename': r.original_filename,
             'state': r.scan_state, 'reason': r.scan_error, 'attempts': r.scan_attempts,
             'created_at': r.created_at} for r in rows]


@router.post('/upload-scanning/{file_id}/retry')
def retry_quarantine(file_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    from sqlalchemy import select, text
    from app.models import File
    from app.upload_scanning import required
    if not required():
        raise HTTPException(409, 'Enable scanning before retrying quarantined uploads')
    try:
        identifier = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(404, 'Upload not found') from None
    row = db.scalar(select(File).where(File.id == identifier).with_for_update())
    if row is None or row.scan_state not in ('error', 'blocked'):
        raise HTTPException(409, 'Upload is not awaiting a retry')
    row.scan_state = 'pending'; row.scan_attempts = 0; row.scan_retry_at = None; row.scan_error = None
    log_event(db, actor_user_id=admin.id, action='file.scan.retry', entity_type='file', entity_id=str(row.id))
    db.execute(text("SELECT pg_notify('canary_upload_scan', '')")); db.commit()
    return {'scan_state': 'pending'}


@router.delete('/upload-scanning/{file_id}', status_code=204)
def discard_quarantined_upload(file_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    from sqlalchemy import select
    from app.models import File
    from app.upload_scanning import quarantine_root
    try:
        identifier = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(404, 'Upload not found') from None
    row = db.scalar(select(File).where(File.id == identifier).with_for_update())
    if row is None or row.scan_state not in ('pending', 'error', 'blocked'):
        raise HTTPException(409, 'Only quarantined uploads can be discarded here')
    if db.scalar(select(File.id).where(File.parent_file_id == row.id).limit(1)):
        raise HTTPException(409, 'Remove the attached files before discarding their parent')
    key = row.scan_quarantine_key
    log_event(db, actor_user_id=admin.id, action='file.scan.discard', entity_type='file', entity_id=str(row.id))
    db.delete(row); db.commit()
    if key and len(key) == 32 and all(c in '0123456789abcdef' for c in key):
        (quarantine_root()/key).unlink(missing_ok=True)
        (quarantine_root()/key).with_suffix('.eml').unlink(missing_ok=True)
