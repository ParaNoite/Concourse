"""数据库引擎与初始化。

SQLite 默认；换 PostgreSQL 只需改 DATABASE_URL（+asyncpg）。
库内 datetime 存 naive UTC，边界由 repository 换算。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from shared import config as cfg

engine = create_async_engine(cfg.secrets.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    # import side-effectful: registers all SQLModel tables on SQLModel.metadata
    import shared.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        # Lightweight column migrations — ALTER TABLE IF NOT EXISTS is not
        # supported in SQLite; instead we probe PRAGMA table_info and add
        # missing columns. Safe to run every startup.
        await conn.run_sync(_migrate_columns)


def _migrate_columns(sync_conn) -> None:  # type: ignore[type-arg]
    """Add columns introduced after initial schema without Alembic."""
    from sqlalchemy import text

    new_columns = [
        ("events",        "course",     "VARCHAR NOT NULL DEFAULT ''"),
        ("staged_events", "course",     "VARCHAR NOT NULL DEFAULT ''"),
        ("events",        "deleted_at", "DATETIME"),
    ]
    for table, col, definition in new_columns:
        rows = sync_conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
        existing = {r[1] for r in rows}
        if col not in existing:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
