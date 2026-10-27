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
