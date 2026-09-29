# keep these models to create tables in db
import app.models.models  # noqa: F401
from app.core.base import Base
from app.core.database import engine

"""
 You can remove this function to create database, if you are using Alembic.
"""


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
