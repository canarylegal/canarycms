"""Unit tests for Radicale htpasswd sync helpers (temp file path)."""

from __future__ import annotations

from pathlib import Path

import bcrypt

from app import radicale_htpasswd as ht


def test_upsert_and_remove_user(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "users"
    monkeypatch.setattr(ht, "_HTPASSWD_PATH", path)

    ht.upsert_user(username="alice", plaintext_password="secret1")
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    user, digest = lines[0].split(":", 1)
    assert user == "alice"
    assert bcrypt.checkpw(b"secret1", digest.encode("ascii"))

    ht.upsert_user(username="bob", plaintext_password="secret2")
    ht.upsert_user(username="alice", plaintext_password="rotated")
    text = path.read_text(encoding="utf-8")
    assert "alice:" in text and "bob:" in text
    alice_line = next(ln for ln in text.splitlines() if ln.startswith("alice:"))
    assert bcrypt.checkpw(b"rotated", alice_line.split(":", 1)[1].encode("ascii"))

    ht.remove_user("bob")
    remaining = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining) == 1
    assert remaining[0].startswith("alice:")

    ht.remove_user("alice")
    assert not path.exists()


def test_remove_user_missing_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "missing-users"
    monkeypatch.setattr(ht, "_HTPASSWD_PATH", path)
    ht.remove_user("nobody")  # no-op
    assert not path.exists()


def test_upsert_rejects_blank_username(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ht, "_HTPASSWD_PATH", tmp_path / "users")
    try:
        ht.upsert_user(username="  ", plaintext_password="x")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "username" in str(exc).lower()
