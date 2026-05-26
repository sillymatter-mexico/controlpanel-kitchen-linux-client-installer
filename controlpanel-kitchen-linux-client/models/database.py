"""Database connection and lifecycle management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Default database path: ~/.cpk/local.db
_DEFAULT_DB_PATH = Path.home() / ".cpk" / "local.db"


def _db_url() -> str:
    """Return the SQLAlchemy async URL for the database, creating parent dirs."""
    path = _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = create_async_engine(_db_url(), echo=False)
_async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def init_db() -> None:
    """Apply all pending Alembic migrations.

    Call once at application startup.  Runs ``alembic upgrade head`` so the
    local database is always up to date with the current schema, whether the
    database is brand-new or was created by an older version of the app.
    """
    import asyncio
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    await asyncio.to_thread(command.upgrade, cfg, "head")


@asynccontextmanager
async def get_db() -> AsyncIterator[AsyncSession]:
    """Async context manager that yields a SQLAlchemy ``AsyncSession``.

    Usage::

        async with get_db() as session:
            result = await session.execute(select(Task))
            tasks = result.scalars().all()
    """
    async with _async_session() as session:
        yield session
