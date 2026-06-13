"""Authenticated staff principal: DB user or master recovery operator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models import User


@dataclass(frozen=True)
class AuthPrincipal:
    is_master_recovery: bool
    user: User | None

    @property
    def actor_user_id(self) -> uuid.UUID | None:
        return None if self.is_master_recovery else (self.user.id if self.user else None)
