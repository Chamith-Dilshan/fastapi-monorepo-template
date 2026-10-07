# keep these models to create tables in db
# import app.models.models  # noqa: F401

# from app.core.base import Base
# from app.core.database import engine

"""
Not called by app.main anymore — schema now comes from Alembic
(`alembic upgrade head`, run by scripts/prestart.sh before the app starts).
Kept only as a quick manual shortcut for local experiments where you don't
want to bother with a migration yet; never use this against a database
Alembic also manages, or the two will disagree about what "head" is.
"""


# async def create_tables() -> None:
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
