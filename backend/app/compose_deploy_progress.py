"""Compose update progress: journal lines → phase for Admin deploy UI."""

from __future__ import annotations

from collections.abc import Callable, MutableSequence
from typing import Literal

ComposeProgressPhase = Literal["git", "build", "up"]


def compose_phase_from_journal(lines: list[str]) -> ComposeProgressPhase:
    """Map live journal lines to coarse Git → Build → Up step."""
    phase: ComposeProgressPhase = "build"
    if any(line.startswith("git:") for line in lines):
        phase = "git"
    for line in lines:
        if line.startswith("git:") and "finished" in line:
            phase = "build"
        elif "docker-compose: build" in line and "(finished)" in line:
            phase = "up"
        elif ("docker-compose: up" in line or "compose up" in line.lower()) and "(starting)" in line:
            phase = "up"
    return phase


class LiveComposeJournal(MutableSequence[str]):
    """Journal list that persists each append for compose-job polling."""

    def __init__(self, job_id: str, on_append: Callable[[str, list[str]], None]) -> None:
        self._job_id = job_id
        self._lines: list[str] = []
        self._on_append = on_append

    def __len__(self) -> int:
        return len(self._lines)

    def __getitem__(self, index: int | slice) -> str | list[str]:
        return self._lines[index]

    def __setitem__(self, index: int | slice, value: object) -> None:
        self._lines[index] = value  # type: ignore[index]

    def __delitem__(self, index: int | slice) -> None:
        del self._lines[index]

    def insert(self, index: int, value: str) -> None:
        self._lines.insert(index, value)

    def append(self, line: str) -> None:
        self._lines.append(line)
        self._on_append(self._job_id, list(self._lines))

    def copy(self) -> list[str]:
        return list(self._lines)
