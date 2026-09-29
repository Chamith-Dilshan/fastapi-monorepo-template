from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.core.exceptions import NotFoundException
from app.models.post_like import PostLike
from app.repositories.post_repository import PostRepository


class PostLikeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.post_repository = PostRepository(db)

    async def get_like(self, user_id: UUID, post_id: UUID) -> PostLike | None:
        post = await self.post_repository.get_model_by_id(post_id)
        if post is None:
            raise NotFoundException(
                message="Post not found",
                status_code=404,
            )

        stmt = select(PostLike).where(
            PostLike.user_id == user_id, PostLike.post_id == post_id
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def add_like(self, like: PostLike) -> PostLike:
        try:
            post = await self.post_repository.get_model_by_id(like.post_id)
            if post is None:
                raise NotFoundException(
                    message="Post not found",
                    status_code=404,
                )

            self.db.add(like)

            await self.db.commit()
            await self.db.refresh(like)

            return like
        except SQLAlchemyError as exc:
            await self.db.rollback()
            raise DatabaseException() from exc

    async def remove_like(self, like: PostLike) -> None:
        post = await self.post_repository.get_model_by_id(like.post_id)
        if post is None:
            raise NotFoundException(
                message="Post not found",
                status_code=404,
            )

        try:
            await self.db.delete(like)
            await self.db.commit()
        except SQLAlchemyError as exc:
            await self.db.rollback()
            raise DatabaseException() from exc
