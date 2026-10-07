from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User) -> User:
        self.db.add(user)

        # flush, not commit — the request-scoped transaction commits once,
        # in app.core.database.get_db, after the whole request succeeds.
        # flush still sends the INSERT and lets server-generated defaults
        # (id, created_at) populate, so the refresh() below works the same
        # as it did with commit(); it just isn't durable/visible to other
        # connections until get_db's commit happens.
        await self.db.flush()
        await self.db.refresh(user)

        return user

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        stmt = select(User).where(User.id == user_id)

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        stmt = select(User).where(User.email == email)

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[User], int]:

        count_stmt = select(func.count()).select_from(User)
        stmt = select(User).offset(skip).limit(limit).order_by(User.created_at.desc())

        total = await self.db.scalar(count_stmt)
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())

        return users, total or 0

    async def delete(
        self,
        user: User,
    ) -> None:
        await self.db.delete(user)
        await self.db.flush()

    async def update(
        self,
        user: User,
    ) -> User:
        await self.db.flush()
        await self.db.refresh(user)

        return user
