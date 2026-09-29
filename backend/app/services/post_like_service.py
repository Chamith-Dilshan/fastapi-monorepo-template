from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.post_like import PostLike
from app.repositories.post_like_repository import PostLikeRepository


class PostLikeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.post_like_repository = PostLikeRepository(db)

    async def toggle_like(self, user_id: UUID, post_id: UUID) -> bool:
        existing_like = await self.post_like_repository.get_like(user_id, post_id)

        if existing_like:
            await self.post_like_repository.remove_like(existing_like)
            return False

        like = PostLike(user_id=user_id, post_id=post_id)

        await self.post_like_repository.add_like(like)

        return True
