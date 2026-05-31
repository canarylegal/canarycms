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
