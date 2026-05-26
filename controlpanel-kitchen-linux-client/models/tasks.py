"""ORM model for the tasks table."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel
from models.database import Base


class Task(BaseModel, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_tasks_status",
        ),
        Index("idx_tasks_status_created", "status", "created_at"),
    )

    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="pending"
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} type={self.type!r} status={self.status!r}>"
