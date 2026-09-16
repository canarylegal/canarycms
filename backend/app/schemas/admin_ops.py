from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class AdminDeployStatusOut(BaseModel):
    """Deploy/update capabilities exposed to admins (no secrets)."""

    configured: bool
    compose_update_enabled: bool = False
    compose_git_reset_enabled: bool = False
    compose_git_ref: str = "main"

class AdminDeployTriggerIn(BaseModel):
    """Legacy body for ``POST /admin/deploy/trigger`` (always returns HTTP 410 — GUI updates removed)."""

    method: Literal["auto", "compose"] = Field(
        default="auto",
        description="Ignored; endpoint is gone.",
    )
    git_strategy: Literal["ff-only", "reset"] = Field(
        default="ff-only",
        description="Ignored; endpoint is gone.",
    )

    model_config = {"extra": "forbid"}

class AdminDeployTriggerOut(BaseModel):
    ok: bool = True
    message: str
    async_mode: bool = False
    job_id: str | None = None

class AdminDeployComposeJobOut(BaseModel):
    """Background compose job status (in-process; single worker recommended)."""

    status: Literal["idle", "running", "succeeded", "failed"]
    job_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    error_detail: str | None = None
    log_excerpt: str | None = None
    journal_lines: list[str] = Field(default_factory=list)
    progress_phase: Literal["git", "build", "up"] | None = None
    elapsed_seconds: float | None = None

class AdminDeployUpdateCheckOut(BaseModel):
    """Admin-only: compare running image commit to GitHub default branch + optional release notes."""

    github_repo_configured: bool
    deploy_trigger_configured: bool = False
    compose_update_enabled: bool = False
    compose_git_reset_enabled: bool = False
    compose_git_ref: str = "main"
    prompt_enabled: bool
    current_commit: str
    current_commit_short: str
    remote_ref: str
    remote_commit: str
    remote_commit_short: str
    update_available: bool
    build_commit_unknown: bool
    compare_html_url: str | None = None
    latest_release_tag: str | None = None
    latest_release_name: str | None = None
    latest_release_body: str | None = None
    commit_messages: list[str] = []
    note: str | None = None

class AdminStorageCategoryOut(BaseModel):
    category: str
    label: str
    bytes_used: int = Field(ge=0)
    file_count: int = Field(ge=0)

class AdminStorageDeploymentComponentOut(BaseModel):
    key: str
    label: str
    bytes_used: int = Field(ge=0)
    detected: bool

class AdminStorageOut(BaseModel):
    tracked_total_bytes: int = Field(ge=0)
    files_on_disk_bytes: int = Field(ge=0)
    compose_mount_bytes: int = Field(ge=0)
    application_checkout_bytes: int = Field(ge=0)
    database_bytes: int | None = Field(default=None, ge=0)
    database_logical_bytes: int | None = Field(default=None, ge=0)
    calendars_bytes: int | None = Field(default=None, ge=0)
    deployment_total_bytes: int = Field(ge=0)
    docker_detected: bool = False
    docker_images_bytes: int = Field(default=0, ge=0)
    docker_container_writable_bytes: int = Field(default=0, ge=0)
    docker_dangling_images_bytes: int = Field(default=0, ge=0)
    docker_build_cache_bytes: int | None = Field(default=None, ge=0)
    deployment_active_bytes: int = Field(default=0, ge=0)
    deployment_artifacts_bytes: int = Field(default=0, ge=0)
    measurement_note: str | None = None
    deployment_components: list[AdminStorageDeploymentComponentOut]
    categories: list[AdminStorageCategoryOut]
    storage_limit_bytes: int | None = None
    files_root: str
    host_disk_detected: bool
    host_disk_total_bytes: int | None = Field(default=None, ge=0)
    host_disk_used_bytes: int | None = Field(default=None, ge=0)
    host_disk_free_bytes: int | None = Field(default=None, ge=0)

class AdminStorageSettingsPatch(BaseModel):
    storage_limit_bytes: int | None = Field(
        default=None,
        ge=1,
        le=10_000_000_000_000_000,
        description="Firm-wide storage quota for tracked files; null clears the limit.",
    )

    model_config = {"extra": "forbid"}
