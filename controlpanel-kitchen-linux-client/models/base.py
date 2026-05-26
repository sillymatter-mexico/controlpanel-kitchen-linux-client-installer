"""Shared ORM mixin with common columns (id, created_at, updated_at)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampedMixin:
    """Adds ``created_at`` and ``updated_at`` columns to any ORM model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class PrimaryKeyMixin:
    """Adds an auto-increment integer ``id`` primary key to any ORM model."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class BaseModel(PrimaryKeyMixin, TimestampedMixin):
    """Convenience mixin combining ``id``, ``created_at``, and ``updated_at``."""
