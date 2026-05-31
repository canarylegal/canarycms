"""Measure Docker Compose stack disk usage via the mounted docker.sock."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from app.compose_runtime import compose_project_dir

_DOCKER_SOCK = "/var/run/docker.sock"
_DOCKER_DU_TIMEOUT = 180.0
_SIZE_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(B|KB|KIB|MB|MIB|GB|GIB|TB|TIB)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DockerImageDiskRow:
    image_id: str
    repository: str
    tag: str
    size_bytes: int
    shared_bytes: int
    unique_bytes: int
    containers: int


@dataclass(frozen=True)
class DockerStackUsage:
    detected: bool
    container_writable_bytes: int
    stack_images_unique_bytes: int
    dangling_images_unique_bytes: int
    build_cache_bytes: int | None
    image_rows: tuple[DockerImageDiskRow, ...]
    container_writable_by_service: dict[str, int]
    note: str | None = None


def docker_sock_available() -> bool:
    return os.path.exists(_DOCKER_SOCK)


def compose_project_name() -> str:
    return (os.getenv("COMPOSE_PROJECT_NAME") or "canary").strip() or "canary"


def _run_docker(args: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_docker_human_size(raw: str) -> int:
    s = raw.strip().split("(", 1)[0].strip().upper().replace(" ", "")
    if not s:
        return 0
    m = _SIZE_RE.match(s)
    if not m:
        return 0
    value = float(m.group(1))
    unit = m.group(2).upper()
    mult = {
        "B": 1,
        "KB": 1024,
        "KIB": 1024,
        "MB": 1024**2,
        "MIB": 1024**2,
        "GB": 1024**3,
        "GIB": 1024**3,
        "TB": 1024**4,
        "TIB": 1024**4,
    }[unit]
    return int(value * mult)


def _short_image_id(image_ref: str) -> str:
    ref = image_ref.strip()
    if ref.startswith("sha256:"):
        return ref.split(":", 1)[1][:12]
    return ref[:12]


def list_compose_container_ids(project: str) -> list[str]:
    proc = _run_docker(
        ["ps", "-a", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"],
        timeout=30,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def list_compose_volume_names(project: str) -> list[str]:
    proc = _run_docker(
        ["volume", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"],
        timeout=30,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def measure_docker_volume_bytes(volume_name: str) -> int | None:
    if not docker_sock_available():
        return None
    inspect = _run_docker(["volume", "inspect", volume_name], timeout=30)
    if inspect.returncode != 0:
        return None
    for image in ("busybox:1.36", "alpine:3.21"):
        proc = _run_docker(
            ["run", "--rm", "-v", f"{volume_name}:/v:ro", image, "du", "-sb", "/v"],
            timeout=_DOCKER_DU_TIMEOUT,
        )
        if proc.returncode != 0:
            continue
        line = proc.stdout.strip().split(maxsplit=1)[0]
        try:
            return int(line)
        except ValueError:
            continue
    return None


def _compose_service_name(container_id: str) -> str:
    proc = _run_docker(
        ["inspect", container_id, "--format", "{{ index .Config.Labels \"com.docker.compose.service\" }}"],
        timeout=15,
    )
    if proc.returncode != 0:
        return container_id[:12]
    name = proc.stdout.strip()
    return name or container_id[:12]


def measure_container_writable_layers(project: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for cid in list_compose_container_ids(project):
        proc = _run_docker(["ps", "-a", "-s", "--filter", f"id={cid}", "--format", "{{.Size}}"], timeout=15)
        if proc.returncode != 0:
            continue
        size_raw = proc.stdout.strip()
        if not size_raw:
            continue
        service = _compose_service_name(cid)
        out[service] = parse_docker_human_size(size_raw)
    return out


def _parse_system_df_images() -> list[DockerImageDiskRow]:
    proc = _run_docker(["system", "df", "-v"], timeout=120)
    if proc.returncode != 0:
        return []
    lines = proc.stdout.splitlines()
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.startswith("REPOSITORY"))
    except StopIteration:
        return []
    rows: list[DockerImageDiskRow] = []
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            break
        if line.startswith("Containers space usage:"):
            break
        parts = line.split()
        if len(parts) < 7:
            continue
        # REPOSITORY TAG IMAGE_ID CREATED SIZE SHARED UNIQUE CONTAINERS
        repository = parts[0]
        tag = parts[1]
        image_id = parts[2]
        size_bytes = parse_docker_human_size(parts[-4])
        shared_bytes = parse_docker_human_size(parts[-3])
        unique_bytes = parse_docker_human_size(parts[-2])
        try:
            containers = int(parts[-1])
        except ValueError:
            containers = 0
        rows.append(
            DockerImageDiskRow(
                image_id=image_id,
                repository=repository,
                tag=tag,
                size_bytes=size_bytes,
                shared_bytes=shared_bytes,
                unique_bytes=unique_bytes,
                containers=containers,
            )
        )
    return rows


def _stack_image_ids(project: str) -> set[str]:
    ids: set[str] = set()
    for cid in list_compose_container_ids(project):
        proc = _run_docker(["inspect", cid, "--format", "{{.Image}}"], timeout=15)
        if proc.returncode != 0:
            continue
        ids.add(_short_image_id(proc.stdout.strip()))
    compose_dir = compose_project_dir()
    if compose_dir.is_dir():
        files_raw = (os.getenv("CANARY_COMPOSE_FILES") or "docker-compose.yml").strip()
        compose_files = [f.strip() for f in files_raw.split(",") if f.strip()]
        args = ["compose", "--project-name", project]
        for cf in compose_files:
            args.extend(["-f", str(compose_dir / cf)])
        args.extend(["images", "-q"])
        proc = _run_docker(args, timeout=60)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    ids.add(_short_image_id(line))
    return ids


def _measure_build_cache_bytes() -> int | None:
    proc = _run_docker(["system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}"], timeout=30)
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Build Cache"):
            parts = line.split("\t")
            if len(parts) >= 2:
                return parse_docker_human_size(parts[1])
    return None


def measure_docker_stack_usage() -> DockerStackUsage:
    if not docker_sock_available():
        return DockerStackUsage(
            detected=False,
            container_writable_bytes=0,
            stack_images_unique_bytes=0,
            dangling_images_unique_bytes=0,
            build_cache_bytes=None,
            image_rows=(),
            container_writable_by_service={},
            note="Docker socket not available.",
        )

    project = compose_project_name()
    image_rows = _parse_system_df_images()
    stack_ids = _stack_image_ids(project)
    writable_by_service = measure_container_writable_layers(project)
    container_writable_bytes = sum(writable_by_service.values())

    stack_images_unique_bytes = 0
    dangling_images_unique_bytes = 0
    for row in image_rows:
        if row.image_id in stack_ids:
            stack_images_unique_bytes += row.unique_bytes
        elif row.repository == "<none>" and row.containers == 0:
            dangling_images_unique_bytes += row.unique_bytes

    build_cache_bytes = _measure_build_cache_bytes()
    note = (
        "Image unique sizes and build cache reflect Docker's accounting on this host. "
        "Shared layers between images are counted once per image unique size; actual disk may be lower. "
        "Dangling images are orphaned layers from past Compose builds on this host."
        if dangling_images_unique_bytes > 0 or (build_cache_bytes or 0) > 0
        else None
    )

    return DockerStackUsage(
        detected=True,
        container_writable_bytes=container_writable_bytes,
        stack_images_unique_bytes=stack_images_unique_bytes,
        dangling_images_unique_bytes=dangling_images_unique_bytes,
        build_cache_bytes=build_cache_bytes,
        image_rows=tuple(image_rows),
        container_writable_by_service=writable_by_service,
        note=note,
    )


def volume_display_label(volume_name: str, project: str) -> str:
    prefix = f"{project}_"
    short = volume_name[len(prefix) :] if volume_name.startswith(prefix) else volume_name
    labels = {
        "db-data": "PostgreSQL data (volume)",
        "radicale-data": "Calendars (CalDAV volume)",
        "frontend-node-modules": "Frontend dev dependencies (volume)",
    }
    return labels.get(short, short.replace("-", " ").replace("_", " ").title() + " (volume)")
