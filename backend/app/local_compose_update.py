"""Run Docker Compose on the host (via mounted docker.sock) for GUI-driven self-hosted updates."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ComposeUpdateConfig:
    project_dir: Path
    compose_files: tuple[str, ...]
    profiles: tuple[str, ...]
    git_pull: bool


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def load_compose_update_config() -> ComposeUpdateConfig | None:
    if not _truthy(os.getenv("CANARY_COMPOSE_UPDATE_ENABLED")):
        return None
    raw = (os.getenv("CANARY_COMPOSE_PROJECT_DIR") or "").strip()
    if not raw:
        return None
    project = Path(raw).resolve()
    if not project.is_dir():
        return None
    files_raw = (os.getenv("CANARY_COMPOSE_FILES") or "docker-compose.yml").strip()
    compose_files = tuple(f.strip() for f in files_raw.split(",") if f.strip())
    if not compose_files:
        compose_files = ("docker-compose.yml",)
    for cf in compose_files:
        if not (project / cf).is_file():
            return None

    prof_raw = (os.getenv("CANARY_COMPOSE_PROFILES") or "prod").strip()
    profiles = tuple(p.strip() for p in prof_raw.replace(",", " ").split() if p.strip())
    if not profiles:
        profiles = ("prod",)

    return ComposeUpdateConfig(
        project_dir=project,
        compose_files=compose_files,
        profiles=profiles,
        git_pull=_truthy(os.getenv("CANARY_COMPOSE_GIT_PULL")),
    )


def compose_update_configured() -> bool:
    return load_compose_update_config() is not None


def _compose_base_cmd(cfg: ComposeUpdateConfig) -> list[str]:
    exe = shutil.which("docker-compose") or "docker-compose"
    cmd: list[str] = [exe]
    for f in cfg.compose_files:
        cmd.extend(["-f", f])
    for p in cfg.profiles:
        cmd.extend(["--profile", p])
    return cmd


def run_compose_update() -> None:
    cfg = load_compose_update_config()
    if cfg is None:
        raise RuntimeError("Docker Compose update is not enabled or project dir is invalid.")

    project_dir = str(cfg.project_dir)
    if cfg.git_pull:
        git = shutil.which("git")
        if not git:
            raise RuntimeError("CANARY_COMPOSE_GIT_PULL is enabled but git is not installed in this container.")
        git_dir = cfg.project_dir / ".git"
        if not git_dir.exists():
            raise RuntimeError("CANARY_COMPOSE_GIT_PULL is set but project dir has no .git directory.")
        try:
            subprocess.run(
                [git, "-C", project_dir, "pull", "--ff-only"],
                check=True,
                timeout=300,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            err = ((e.stderr or "") + (e.stdout or "")).strip()[-4000:]
            raise RuntimeError(f"git pull failed: {err or e.returncode}") from e

    base = _compose_base_cmd(cfg)
    env = os.environ.copy()

    def _run(step: list[str], timeout: int) -> None:
        try:
            subprocess.run(
                base + step,
                cwd=project_dir,
                check=True,
                timeout=timeout,
                env=env,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            err = ((e.stderr or "") + (e.stdout or "")).strip()[-8000:]
            raise RuntimeError(f"docker-compose {' '.join(step)} failed: {err or e.returncode}") from e

    _run(["build", "--pull"], 3600)
    _run(["up", "-d"], 900)
