"""Run Docker Compose on the host (via mounted docker.sock) for GUI-driven self-hosted updates."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, MutableSequence

GitSyncStrategy = Literal["ff-only", "reset", "none"]


@dataclass(frozen=True)
class ComposeUpdateConfig:
    project_dir: Path
    compose_files: tuple[str, ...]
    profiles: tuple[str, ...]
    git_pull: bool
    git_reset_enabled: bool
    git_ref: str


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
        git_reset_enabled=_truthy(os.getenv("CANARY_COMPOSE_GIT_RESET_ENABLED")),
        git_ref=(os.getenv("CANARY_GITHUB_DEPLOY_REF") or "main").strip() or "main",
    )


def compose_git_reset_enabled() -> bool:
    """True when admins may request ``git fetch`` + ``reset --hard`` before compose (see ``CANARY_COMPOSE_GIT_RESET_ENABLED``)."""
    cfg = load_compose_update_config()
    return cfg is not None and cfg.git_reset_enabled


def compose_update_configured() -> bool:
    return load_compose_update_config() is not None


def _git_trust_repo_args(repo: Path) -> list[str]:
    """Skip Git 2.35+ "dubious ownership" when the repo is bind-mounted (host uid ≠ container user).

    ``-c`` must come before ``-C`` so Git applies ``safe.directory`` before entering the repo.
    """
    root = str(repo.resolve())
    return ["-c", f"safe.directory={root}", "-C", root]


def _inject_git_commit_for_compose_build(env: dict[str, str], project_dir: Path) -> None:
    """Set GIT_COMMIT for ``docker compose build`` so the backend image bakes the checkout SHA.

    Without this, Compose variable substitution often falls back to ``${GIT_COMMIT:-unknown}`` from a
    stale host ``.env`` or an empty environment, so the running app keeps reporting an old commit and
    the admin UI falsely shows an update available.
    """
    if not (project_dir / ".git").exists():
        return
    git = shutil.which("git")
    if not git:
        return
    try:
        r = subprocess.run(
            [git, *_git_trust_repo_args(project_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        sha = (r.stdout or "").strip()
        if len(sha) >= 7:
            env["GIT_COMMIT"] = sha
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return


def compose_project_git_head() -> str | None:
    """``git rev-parse HEAD`` at :envvar:`CANARY_COMPOSE_PROJECT_DIR` when that path is a git checkout.

    Does **not** require ``CANARY_COMPOSE_UPDATE_ENABLED`` — many stacks mount the repo for deploy tooling
    but leave GUI compose updates off; Admin → Deploy still needs the real checkout SHA.
    """
    raw = (os.getenv("CANARY_COMPOSE_PROJECT_DIR") or "").strip()
    if not raw:
        return None
    repo = Path(raw).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        return None
    git = shutil.which("git")
    if not git:
        return None
    try:
        r = subprocess.run(
            [git, *_git_trust_repo_args(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        sha = (r.stdout or "").strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return sha if len(sha) >= 7 else None


def _compose_base_cmd(cfg: ComposeUpdateConfig) -> list[str]:
    exe = shutil.which("docker-compose") or "docker-compose"
    cmd: list[str] = [exe]
    for f in cfg.compose_files:
        cmd.extend(["-f", f])
    for p in cfg.profiles:
        cmd.extend(["--profile", p])
    return cmd


def _compose_inner_cli_parts(cfg: ComposeUpdateConfig) -> list[str]:
    """Arguments for ``docker compose`` (v2 CLI) inside a one-shot runner container."""
    parts: list[str] = ["docker", "compose"]
    for f in cfg.compose_files:
        parts.extend(["-f", f])
    for p in cfg.profiles:
        parts.extend(["--profile", p])
    return parts


def _in_container() -> bool:
    return Path("/.dockerenv").is_file()


def _normalize_mount_root_for_docker_bind(path: str) -> str:
    """Map btrfs (and similar) subvolume roots from mountinfo to host paths Docker can bind-mount.

    On some Linux installs ``/proc/self/mountinfo`` reports e.g. ``/@home/colin/proj`` while the daemon
    only accepts ``/home/colin/proj`` for ``docker run -v``.
    """
    p = path.strip()
    if p.startswith("/@home"):
        return "/home" + p[len("/@home") :]
    return p


def _host_path_for_compose_project(container_project: Path) -> str:
    """Path on the Docker host for bind-mounting the compose project into a sibling container.

    ``docker run -v`` sources are resolved on the daemon host. When the backend only sees
    ``/canary-compose``, map it via ``/proc/self/mountinfo`` unless ``CANARY_COMPOSE_HOST_PROJECT_DIR``
    is set (compose project dir only — not ``FILES_ROOT``, which is usually a separate mount).
    """
    target = str(container_project.resolve())
    explicit = (os.getenv("CANARY_COMPOSE_HOST_PROJECT_DIR") or "").strip()
    compose_dir_raw = (os.getenv("CANARY_COMPOSE_PROJECT_DIR") or "/canary-compose").strip()
    if explicit and compose_dir_raw:
        try:
            compose_mp = str(Path(compose_dir_raw).resolve())
            if target == compose_mp or target.startswith(compose_mp.rstrip("/") + "/"):
                host_root = Path(explicit).resolve()
                if target == compose_mp:
                    return _normalize_mount_root_for_docker_bind(str(host_root))
                rel = Path(target).relative_to(compose_mp)
                return _normalize_mount_root_for_docker_bind(str(host_root / rel))
        except (ValueError, OSError):
            pass
    best_mp = ""
    best_root = ""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as f:
            for raw in f:
                parts = raw.split()
                if len(parts) < 10:
                    continue
                root = parts[3]
                mp = parts[4]
                if not (target == mp or target.startswith(mp + "/")):
                    continue
                if len(mp) > len(best_mp):
                    best_mp = mp
                    best_root = root
    except OSError:
        return _normalize_mount_root_for_docker_bind(target)
    if not best_mp:
        return _normalize_mount_root_for_docker_bind(target)
    if target == best_mp:
        return _normalize_mount_root_for_docker_bind(str(Path(best_root).resolve()))
    rel = target[len(best_mp) :].lstrip("/")
    return _normalize_mount_root_for_docker_bind(str((Path(best_root) / rel).resolve()))


def _isolated_compose_up_enabled() -> bool:
    raw = (os.getenv("CANARY_COMPOSE_ISOLATED_UP") or "").strip()
    if not raw:
        raw = "1" if _in_container() else "0"
    if not _truthy(raw):
        return False
    return Path("/var/run/docker.sock").exists()


def compose_runner_container_name(job_id: str) -> str:
    return f"canary-compose-up-{job_id}"


def docker_inspect_container_state(name: str) -> tuple[str, int | None] | None:
    """Return ``(status, exit_code)`` for a container, or ``None`` if it does not exist."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    parts = (r.stdout or "").strip().split()
    if len(parts) < 2:
        return None
    st, ec_s = parts[0], parts[1]
    try:
        ec = int(ec_s)
    except ValueError:
        ec = None
    return st, ec


def _run_compose_up_isolated(
    cfg: ComposeUpdateConfig,
    *,
    journal: MutableSequence[str] | None,
    env: dict[str, str],
    timeout: int,
    compose_job_id: str,
) -> None:
    """Run ``up -d`` in a **detached** sibling container and wait via marker file + ``docker inspect``.

    A foreground ``docker run`` still runs inside this backend process; when Compose recreates the
    backend, this process can be SIGKILL'd before ``docker run`` returns. The detached runner keeps
    going and writes a JSON marker under the compose runtime dir; :mod:`app.compose_deploy_job` reconciles
    that on startup and when polling job status.
    """
    from app.compose_runtime import (
        compose_runtime_dir,
        compose_up_marker_basename,
        compose_up_marker_path,
        resolve_compose_up_marker,
    )

    inner = _compose_inner_cli_parts(cfg) + ["up", "-d"]
    inner_sh = shlex.join(inner)
    host_project = _host_path_for_compose_project(cfg.project_dir)
    runtime_dir = compose_runtime_dir()
    runtime_in_container = str(runtime_dir)
    host_runtime = _host_path_for_compose_project(runtime_dir)
    image = (os.getenv("CANARY_COMPOSE_RUNNER_IMAGE") or "docker:27-cli").strip()
    name = compose_runner_container_name(compose_job_id)
    marker = compose_up_marker_path(compose_job_id)
    marker.unlink(missing_ok=True)
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, text=True, timeout=60)

    # shell: run compose then write marker (atomic enough for our readers)
    marker_fn = compose_up_marker_basename(compose_job_id)
    shell = (
        f'f="${{CANARY_COMPOSE_RUNTIME_DIR}}/{marker_fn}"; set +e; {inner_sh}; rc=$?; '
        + 'if [ "$rc" -eq 0 ]; then echo \'{"ok":true,"rc":0}\' > "$f"; '
        + 'else printf \'{"ok":false,"rc":%s}\\n\' "$rc" > "$f"; fi; exit "$rc"'
    )

    cmd: list[str] = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        f"{host_project}:{host_project}",
        "-v",
        f"{host_runtime}:{runtime_in_container}",
        "-w",
        host_project,
        "-e",
        f"CANARY_COMPOSE_RUNTIME_DIR={runtime_in_container}",
    ]
    env_file = cfg.project_dir / ".env"
    if env_file.is_file():
        cmd.extend(["--env-file", str(env_file)])
    for key in ("COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "COMPOSE_FILE", "DOCKER_DEFAULT_PLATFORM"):
        val = (os.environ.get(key) or "").strip()
        if val:
            cmd.extend(["-e", f"{key}={val}"])
    gc = (env.get("GIT_COMMIT") or "").strip()
    if gc:
        cmd.extend(["-e", f"GIT_COMMIT={gc}"])
    cmd.extend([image, "sh", "-c", shell])
    _journal(
        journal,
        f"docker compose up (detached isolated runner {name}): {image} {inner_sh} (starting)",
    )
    try:
        subprocess.run(cmd, check=True, timeout=120, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err = ((e.stderr or "") + (e.stdout or "")).strip()[-8000:]
        raise RuntimeError(f"starting isolated compose runner failed: {err or e.returncode}") from e

    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        found = resolve_compose_up_marker(compose_job_id)
        if found is not None:
            try:
                row = json.loads(found.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise RuntimeError(f"invalid compose-up marker file: {e}") from e
            found.unlink(missing_ok=True)
            subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, text=True, timeout=60)
            if not bool(row.get("ok")):
                rc = row.get("rc")
                raise RuntimeError(f"docker compose up -d failed (rc={rc})")
            _journal(journal, "docker compose up (isolated runner): finished")
            return

        st = docker_inspect_container_state(name)
        if st is not None and st[0] == "exited":
            # Runner exited before marker visible — brief race, or another coroutine consumed the marker.
            time.sleep(0.4)
            if resolve_compose_up_marker(compose_job_id) is not None:
                continue
            from app.compose_deploy_job import compose_job_disk_says_running, reconcile_compose_job_state

            reconcile_compose_job_state()
            if not compose_job_disk_says_running():
                _journal(journal, "compose up: job finalized via reconcile (marker consumed elsewhere)")
                return
            subprocess.run(["docker", "logs", "--tail", "120", name], check=False, capture_output=True, text=True, timeout=30)
            raise RuntimeError(
                "compose runner container exited without writing a success marker "
                f"(exit_code={st[1]}); check ``docker logs {name}`` on the host."
            )

        time.sleep(2.0)

    raise RuntimeError(
        f"timed out after {timeout}s waiting for compose up (runner {name}, marker {marker}). "
        "The runner may still be running; check ``docker ps -a`` on the host."
    )


def _journal(journal: MutableSequence[str] | None, line: str) -> None:
    if journal is not None:
        journal.append(line)


def _git_sync_error_detail(exc: subprocess.CalledProcessError) -> str:
    return ((exc.stderr or "") + (exc.stdout or "")).strip()[-4000:]


def _subprocess_failure_message(step_label: str, exc: subprocess.CalledProcessError) -> str:
    """Prefer compile/build error lines over a wall of pip/npm download output."""
    combined = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip()
    highlights: list[str] = []
    for line in combined.splitlines():
        s = line.strip()
        if not s:
            continue
        lower = s.lower()
        if (
            "error ts" in lower
            or s.startswith("ERROR:")
            or "npm err!" in lower
            or "error:" in lower
            or "failed to solve" in lower
            or "did not complete successfully" in lower
        ):
            highlights.append(s)
    if highlights:
        body = "\n".join(highlights[-12:])
        return f"{step_label} failed (exit {exc.returncode}):\n{body}"
    tail = combined[-2500:] if combined else ""
    return f"{step_label} failed (exit {exc.returncode}): {tail or 'no output captured'}"


def _run_git_sync(cfg: ComposeUpdateConfig, journal: MutableSequence[str] | None, strategy: GitSyncStrategy) -> None:
    if strategy == "none":
        return
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is not installed in this container.")
    git_dir = cfg.project_dir / ".git"
    if not git_dir.exists():
        raise RuntimeError("Compose project dir has no .git directory.")
    trust = _git_trust_repo_args(cfg.project_dir)

    if strategy == "ff-only":
        _journal(journal, "git: pull --ff-only (starting)")
        try:
            subprocess.run(
                [git, *trust, "pull", "--ff-only"],
                check=True,
                timeout=300,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            err = _git_sync_error_detail(e)
            if cfg.git_reset_enabled:
                _journal(
                    journal,
                    "git: pull --ff-only failed (checkout diverged from origin); "
                    "falling back to fetch + reset --hard",
                )
                _run_git_sync(cfg, journal, "reset")
                return
            raise RuntimeError(f"git pull failed: {err or e.returncode}") from e
        _journal(journal, "git: pull finished")
        return

    ref = cfg.git_ref
    _journal(journal, f"git: fetch origin {ref} + reset --hard FETCH_HEAD (starting)")
    try:
        subprocess.run(
            [git, *trust, "fetch", "origin", ref],
            check=True,
            timeout=300,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [git, *trust, "reset", "--hard", "FETCH_HEAD"],
            check=True,
            timeout=120,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        err = _git_sync_error_detail(e)
        raise RuntimeError(f"git reset to origin/{ref} failed: {err or e.returncode}") from e
    _journal(journal, f"git: reset finished (origin/{ref})")


def run_compose_update(
    *,
    journal: MutableSequence[str] | None = None,
    compose_job_id: str | None = None,
    on_after_build_before_compose_up: Callable[[], None] | None = None,
    git_strategy: GitSyncStrategy = "ff-only",
) -> None:
    cfg = load_compose_update_config()
    if cfg is None:
        raise RuntimeError("Docker Compose update is not enabled or project dir is invalid.")

    if git_strategy == "reset":
        if not cfg.git_reset_enabled:
            raise RuntimeError(
                "Git reset is not enabled. Set CANARY_COMPOSE_GIT_RESET_ENABLED=1 (see .env.example)."
            )
        _run_git_sync(cfg, journal, "reset")
    elif cfg.git_pull:
        _run_git_sync(cfg, journal, "ff-only")

    project_dir = str(cfg.project_dir)
    base = _compose_base_cmd(cfg)
    env = os.environ.copy()
    _inject_git_commit_for_compose_build(env, cfg.project_dir)

    def _run(step: list[str], timeout: int) -> None:
        _journal(journal, f"docker-compose: {' '.join(step)} (starting)")
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
            msg = _subprocess_failure_message(f"docker-compose {' '.join(step)}", e)
            _journal(journal, msg.splitlines()[0])
            for line in msg.splitlines()[1:]:
                if line.strip():
                    _journal(journal, line.strip())
            raise RuntimeError(msg) from e
        _journal(journal, f"docker-compose: {' '.join(step)} (finished)")

    _run(["build", "--pull"], 3600)
    if _isolated_compose_up_enabled():
        jid = (compose_job_id or "").strip() or uuid.uuid4().hex[:12]
        if on_after_build_before_compose_up is not None:
            on_after_build_before_compose_up()
        _run_compose_up_isolated(cfg, journal=journal, env=env, timeout=900, compose_job_id=jid)
    else:
        _run(["up", "-d"], 900)
