from uuid import UUID

from sqlalchemy import func, select, case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DatabaseException
from app.custom_types.post_types import PostWithLikeData
from app.models.post import Post
from app.models.post_like import PostLike


class PostRepository:
    """
    Projection Query
    ================

    A projection query is a query that returns an entity together with
    additional computed or aggregated data required by the application.

    Example:

        Post
        + Author
        + Like Count
        + Is Liked

    instead of only:

        Post

    Projection queries are commonly used in feed-based applications
    because API responses often require information from multiple tables.

    Examples:

        Instagram Feed
            Post + Author + Like Count + Is Liked

        Twitter Timeline
            Tweet + Author + Retweet Count + Is Following

        LinkedIn Feed
            Post + Author + Reaction Count + Is Connected

    The projection query acts as the single source of truth for all
    read operations that return posts.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, post: Post) -> Post:
        try:
            self.db.add(post)
            await self.db.commit()
            await self.db.refresh(post)
            return post

        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    async def get_by_id(
        self, post_id: UUID, viewer_id: UUID
    ) -> PostWithLikeData | None:
        stmt = self._posts_query(viewer_id).where(Post.id == post_id)

        try:
            result = await self.db.execute(stmt)

            row = result.one_or_none()

            if row is None:
                return None

            post, like_count, is_liked = row

            return {
                "post": post,
                "like_count": like_count,
                "is_liked": is_liked,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    async def get_model_by_id(
        self,
        post_id: UUID,
    ) -> Post | None:

        try:
            stmt = (
                select(Post)
                .options(selectinload(Post.author))
                .where(Post.id == post_id)
            )

            result = await self.db.execute(stmt)

            return result.scalar_one_or_none()

        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    @staticmethod
    def _posts_query(viewer_id: UUID):
        """
        Base projection query used by all post read operations.

        Purpose
        -------
        This query returns a Post together with additional feed metadata
        required by the API response.

        Returned Data
        -------------
        - Post model
        - like_count: Total number of likes for the post
        - is_liked: Whether the current viewer has liked the post

        Relationships
        -------------
        Author data is loaded using:

            selectinload(Post.author)

        This uses the SQLAlchemy relationship defined as:

            Post.author <-> User.posts

        allowing PostResponse.author to be populated without additional
        manual queries.

        Like Aggregation
        ----------------
        Like count is calculated in the database using:

            COUNT(PostLike.user_id)

        instead of loading all PostLike records into memory.

        Viewer Context
        --------------
        The viewer_id parameter represents the currently authenticated user.

        It is used to calculate:

            is_liked = True

        when a PostLike record exists between:

            viewer_id -> post_id

        Query Strategy
        --------------
        This is a projection query, not a pure entity query.

        The goal is to return exactly the data required by the API layer:

            Post
            + Author
            + Like Count
            + Is Liked

        in a single database query.

        This query is reused by:

            - get_post_projection()
            - get_posts_by_author()
            - get_all_posts()

        Performance Notes
        -----------------
        Relationships are used for loading related entities
        (Post -> Author).

        Aggregated values such as:

            - like_count
            - is_liked

        are computed directly by SQL rather than loading all likes and
        calculating them in Python.

        This avoids N+1 query problems and unnecessary memory usage.

        Future Extensions
        -----------------
        Additional feed metadata can be added here without changing
        service or API layers:

            - comment_count
            - bookmark_count
            - share_count
            - is_bookmarked
            - is_following_author

        making this query the single source of truth for post responses.
        """

        return (
            select(
                Post,
                func.count(PostLike.post_id).label("like_count"),
                (
                    func.max(
                        case(
                            (PostLike.user_id == viewer_id, 1),
                            else_=0,
                        )
                    )
                    == 1
                ).label("is_liked"),
            )
            .outerjoin(
                PostLike,
                Post.id == PostLike.post_id,
            )
            .options(
                selectinload(Post.author),
            )
            .group_by(Post.id)
        )

    @staticmethod
    def _map_post_rows(rows) -> list[PostWithLikeData]:
        return [
            PostWithLikeData(
                post=post,
                like_count=like_count,
                is_liked=is_liked,
            )
            for post, like_count, is_liked in rows
        ]

    async def get_posts_by_author(
        self,
        author_id: UUID,
        viewer_id: UUID,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
    ) -> tuple[list[PostWithLikeData], int]:

        stmt = (
            self._posts_query(viewer_id)
            .where(Post.author_id == author_id)
            .order_by(Post.created_at.desc())
        )

        count_stmt = (
            select(func.count()).select_from(Post).where(Post.author_id == author_id)
        )

        if search:
            search_filter = Post.title.ilike(f"%{search}%")

            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        stmt = stmt.offset(skip).limit(limit)

        try:
            total = await self.db.scalar(count_stmt)

            result = await self.db.execute(stmt)

            rows = result.all()

            return self._map_post_rows(rows), total or 0

        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    async def get_all_posts(
        self,
        viewer_id: UUID,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
    ) -> tuple[list[PostWithLikeData], int]:

        stmt = self._posts_query(viewer_id).order_by(Post.created_at.desc())

        count_stmt = select(func.count()).select_from(Post)

        if search:
            search_filter = Post.title.ilike(f"%{search}%")

            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        stmt = stmt.offset(skip).limit(limit)

        try:
            total = await self.db.scalar(count_stmt)

            result = await self.db.execute(stmt)

            rows = result.all()

            return self._map_post_rows(rows), total or 0

        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    async def delete(self, post: Post) -> None:
        try:
            await self.db.delete(post)
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e

    async def update(self, post: Post) -> Post:
        try:
            await self.db.commit()
            await self.db.refresh(post)
            return post
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise DatabaseException() from e
