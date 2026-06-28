"""Aggregate Canary file storage usage for admin reporting."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.compose_runtime import compose_project_dir
from app.docker_stack_usage import (
    compose_project_name,
    docker_sock_available,
    measure_container_writable_layers,
    measure_docker_stack_usage,
    measure_docker_volume_bytes,
    volume_display_label,
)
from app.file_storage import FILES_ROOT
from app.models import File, FileCategory

_DOCKER_DU_TIMEOUT = 180.0


@dataclass(frozen=True)
class StorageCategoryUsage:
    category: str
    label: str
    bytes_used: int
    file_count: int


@dataclass(frozen=True)
class DeploymentComponentUsage:
    key: str
    label: str
    bytes_used: int
    detected: bool


@dataclass(frozen=True)
class DeploymentStorageSnapshot:
    components: list[DeploymentComponentUsage]
    deployment_total_bytes: int
    compose_mount_bytes: int
    application_checkout_bytes: int
    files_on_disk_bytes: int
    database_on_disk_bytes: int | None
    database_logical_bytes: int | None
    calendars_bytes: int | None
    docker_detected: bool
    docker_images_bytes: int
    docker_container_writable_bytes: int
    docker_dangling_images_bytes: int
    docker_build_cache_bytes: int | None
    deployment_active_bytes: int
    deployment_artifacts_bytes: int
    measurement_note: str | None


_CATEGORY_LABELS: dict[FileCategory, str] = {
    FileCategory.case_document: "Case documents",
    FileCategory.precedent: "Precedents",
    FileCategory.firm_letterhead: "Firm letterhead",
    FileCategory.firm_portal_logo: "Portal logo",
    FileCategory.fee_scale: "Fee scales",
    FileCategory.system: "System",
    FileCategory.user_signature: "User signatures",
}


def aggregate_storage_by_category(db: Session) -> list[StorageCategoryUsage]:
    rows = db.execute(
        select(File.category, func.count(File.id), func.coalesce(func.sum(File.size_bytes), 0)).group_by(File.category)
    ).all()
    by_cat = {cat: (int(count), int(total)) for cat, count, total in rows}
    out: list[StorageCategoryUsage] = []
    for cat in FileCategory:
        count, total = by_cat.get(cat, (0, 0))
        out.append(
            StorageCategoryUsage(
                category=cat.value,
                label=_CATEGORY_LABELS[cat],
                bytes_used=total,
                file_count=count,
            )
        )
    return out


def total_tracked_bytes(categories: list[StorageCategoryUsage]) -> int:
    return sum(c.bytes_used for c in categories)


def walk_directory_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in filenames:
            try:
                total += (base / name).stat().st_size
            except OSError:
                continue
    return total


def measure_postgres_logical_bytes(db: Session) -> int | None:
    try:
        value = db.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        return int(value)
    except Exception:
        return None


def radicale_data_root() -> Path:
    raw = (os.getenv("RADICALE_HTPASSWD_PATH") or "/radicale-data/users").strip()
    return Path(raw).resolve().parent


def measure_deployment_storage(db: Session) -> DeploymentStorageSnapshot:
    from app.docker_stack_usage import list_compose_volume_names

    compose_root = compose_project_dir()
    compose_mount_bytes = walk_directory_bytes(compose_root) if compose_root.is_dir() else 0
    files_on_disk_bytes = walk_directory_bytes(FILES_ROOT) if FILES_ROOT.is_dir() else 0
    application_checkout_bytes = max(0, compose_mount_bytes - files_on_disk_bytes)

    database_logical_bytes = measure_postgres_logical_bytes(db)
    project = compose_project_name()
    docker_stack = measure_docker_stack_usage()

    database_on_disk_bytes: int | None = None
    calendars_bytes: int | None = None
    for vol in list_compose_volume_names(project):
        vol_bytes = measure_docker_volume_bytes(vol)
        if vol_bytes is None:
            continue
        short = vol.removeprefix(f"{project}_")
        if short == "db-data":
            database_on_disk_bytes = vol_bytes
        elif short == "radicale-data":
            calendars_bytes = vol_bytes

    if database_on_disk_bytes is None:
        database_on_disk_bytes = database_logical_bytes
    if calendars_bytes is None:
        calendars_root = radicale_data_root()
        calendars_bytes = walk_directory_bytes(calendars_root) if calendars_root.is_dir() else None

    components: list[DeploymentComponentUsage] = []

    if files_on_disk_bytes > 0 or FILES_ROOT.is_dir():
        components.append(
            DeploymentComponentUsage(
                key="files",
                label="Stored files (bind mount)",
                bytes_used=files_on_disk_bytes,
                detected=FILES_ROOT.is_dir(),
            )
        )

    if application_checkout_bytes > 0 or compose_root.is_dir():
        components.append(
            DeploymentComponentUsage(
                key="application",
                label="Application checkout (bind mount)",
                bytes_used=application_checkout_bytes,
                detected=compose_root.is_dir(),
            )
        )

    for vol in list_compose_volume_names(project):
        vol_bytes = measure_docker_volume_bytes(vol)
        if vol_bytes is None:
            continue
        short = vol.removeprefix(f"{project}_")
        components.append(
            DeploymentComponentUsage(
                key=f"volume_{short.replace('-', '_')}",
                label=volume_display_label(vol, project),
                bytes_used=vol_bytes,
                detected=True,
            )
        )

    if docker_stack.detected:
        if docker_stack.stack_images_unique_bytes > 0:
            components.append(
                DeploymentComponentUsage(
                    key="docker_images",
                    label="Docker images (stack)",
                    bytes_used=docker_stack.stack_images_unique_bytes,
                    detected=True,
                )
            )

        for service, rw_bytes in sorted(docker_stack.container_writable_by_service.items()):
            if rw_bytes <= 0:
                continue
            components.append(
                DeploymentComponentUsage(
                    key=f"container_{service}",
                    label=f"Container data ({service})",
                    bytes_used=rw_bytes,
                    detected=True,
                )
            )

        if docker_stack.dangling_images_unique_bytes > 0:
            components.append(
                DeploymentComponentUsage(
                    key="docker_dangling",
                    label="Orphaned Docker build layers",
                    bytes_used=docker_stack.dangling_images_unique_bytes,
                    detected=True,
                )
            )

        if docker_stack.build_cache_bytes and docker_stack.build_cache_bytes > 0:
            components.append(
                DeploymentComponentUsage(
                    key="docker_build_cache",
                    label="Docker build cache (host)",
                    bytes_used=docker_stack.build_cache_bytes,
                    detected=True,
                )
            )
    elif database_on_disk_bytes is not None and not any(c.key.startswith("volume_") for c in components):
        components.append(
            DeploymentComponentUsage(
                key="database",
                label="PostgreSQL database (logical size)"
                if database_logical_bytes == database_on_disk_bytes
                else "PostgreSQL data",
                bytes_used=database_on_disk_bytes,
                detected=True,
            )
        )
        if calendars_bytes is not None:
            components.append(
                DeploymentComponentUsage(
                    key="calendars",
                    label="Calendars (CalDAV)",
                    bytes_used=calendars_bytes,
                    detected=True,
                )
            )

    deployment_total_bytes = sum(c.bytes_used for c in components if c.detected)
    artifact_keys = frozenset({"docker_dangling", "docker_build_cache"})
    deployment_active_bytes = sum(c.bytes_used for c in components if c.detected and c.key not in artifact_keys)
    deployment_artifacts_bytes = sum(c.bytes_used for c in components if c.detected and c.key in artifact_keys)

    notes: list[str] = []
    if docker_stack.note:
        notes.append(docker_stack.note)
    if not docker_sock_available():
        notes.append(
            "Mount /var/run/docker.sock into the backend to include Docker images, container layers, and build cache."
        )
    if application_checkout_bytes > 50 * 1024**2:
        notes.append(
            "Application checkout includes local dev tooling (e.g. backend/.venv) when present on the bind-mounted project directory."
        )

    return DeploymentStorageSnapshot(
        components=components,
        deployment_total_bytes=deployment_total_bytes,
        compose_mount_bytes=compose_mount_bytes,
        application_checkout_bytes=application_checkout_bytes,
        files_on_disk_bytes=files_on_disk_bytes,
        database_on_disk_bytes=database_on_disk_bytes,
        database_logical_bytes=database_logical_bytes,
        calendars_bytes=calendars_bytes,
        docker_detected=docker_stack.detected,
        docker_images_bytes=docker_stack.stack_images_unique_bytes,
        docker_container_writable_bytes=docker_stack.container_writable_bytes,
        docker_dangling_images_bytes=docker_stack.dangling_images_unique_bytes,
        docker_build_cache_bytes=docker_stack.build_cache_bytes,
        deployment_active_bytes=deployment_active_bytes,
        deployment_artifacts_bytes=deployment_artifacts_bytes,
        measurement_note=" ".join(notes) if notes else None,
    )


def detect_files_root_disk() -> tuple[bool, int | None, int | None, int | None]:
    """Return (detected, total_bytes, used_bytes, free_bytes) for the FILES_ROOT mount."""
    try:
        usage = shutil.disk_usage(FILES_ROOT)
    except OSError:
        return False, None, None, None
    total = int(usage.total)
    free = int(usage.free)
    used = max(0, total - free)
    return True, total, used, free
