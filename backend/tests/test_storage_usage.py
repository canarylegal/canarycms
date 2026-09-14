"""Storage usage aggregation tests."""

from pathlib import Path
from unittest.mock import patch

from app.docker_stack_usage import parse_docker_human_size
from app.storage_usage import measure_deployment_storage, walk_directory_bytes, _CATEGORY_LABELS
from app.models import FileCategory


def test_category_labels_cover_all_enums() -> None:
    assert set(_CATEGORY_LABELS.keys()) == set(FileCategory)


def test_parse_docker_human_size() -> None:
    assert parse_docker_human_size("696MB (virtual 4.66GB)") == 696 * 1024**2
    assert parse_docker_human_size("4.1kB") == int(4.1 * 1024)


def test_walk_directory_bytes_sums_files(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"12345")
    assert walk_directory_bytes(tmp_path) == 5


def test_measure_deployment_storage_splits_compose_and_files(tmp_path: Path, monkeypatch) -> None:
    compose = tmp_path / "compose"
    files = compose / "data" / "files"
    files.mkdir(parents=True)
    (files / "doc.bin").write_bytes(b"x" * 100)
    (compose / "backend").mkdir()
    (compose / "backend" / "main.py").write_bytes(b"print('hi')")

    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(compose))
    monkeypatch.setenv("FILES_ROOT", str(files))
    monkeypatch.setattr("app.storage_usage.FILES_ROOT", files)

    class _Db:
        pass

    with patch("app.storage_usage.measure_postgres_logical_bytes", return_value=500), patch(
        "app.storage_usage.measure_docker_stack_usage"
    ) as mock_stack, patch("app.docker_stack_usage.list_compose_volume_names", return_value=[]):
        from app.docker_stack_usage import DockerStackUsage

        mock_stack.return_value = DockerStackUsage(
            detected=False,
            container_writable_bytes=0,
            stack_images_unique_bytes=0,
            dangling_images_unique_bytes=0,
            build_cache_bytes=None,
            image_rows=(),
            container_writable_by_service={},
        )
        snap = measure_deployment_storage(_Db())  # type: ignore[arg-type]

    assert snap.files_on_disk_bytes == 100
    assert snap.application_checkout_bytes == len(b"print('hi')")


def test_list_compose_volume_names_without_docker_cli() -> None:
    """Admin → Storage must not 500 when docker.sock/CLI are absent (default prod)."""
    from app.docker_stack_usage import list_compose_volume_names, _run_docker

    with patch("app.docker_stack_usage.docker_sock_available", return_value=False):
        assert list_compose_volume_names("canary") == []

    with patch("app.docker_stack_usage.docker_sock_available", return_value=True), patch(
        "app.docker_stack_usage.subprocess.run", side_effect=FileNotFoundError("docker")
    ):
        result = _run_docker(["volume", "ls"])
        assert result.returncode == 127
        assert list_compose_volume_names("canary") == []


def test_measure_deployment_storage_without_docker(tmp_path: Path, monkeypatch) -> None:
    compose = tmp_path / "compose"
    files = compose / "data" / "files"
    files.mkdir(parents=True)
    (files / "doc.bin").write_bytes(b"hello")
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(compose))
    monkeypatch.setattr("app.storage_usage.FILES_ROOT", files)

    class _Db:
        pass

    with patch("app.storage_usage.measure_postgres_logical_bytes", return_value=42), patch(
        "app.storage_usage.docker_sock_available", return_value=False
    ), patch("app.docker_stack_usage.docker_sock_available", return_value=False), patch(
        "app.docker_stack_usage.subprocess.run", side_effect=FileNotFoundError("docker")
    ):
        snap = measure_deployment_storage(_Db())  # type: ignore[arg-type]

    assert snap.docker_detected is False
    assert snap.files_on_disk_bytes == 5
    assert snap.database_logical_bytes == 42
    note = (snap.measurement_note or "").lower()
    assert "docker socket" in note or "docker.sock" in note
