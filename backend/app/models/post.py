from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.post_like import PostLike


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    content: Mapped[str] = mapped_column(nullable=False)

    published: Mapped[bool] = mapped_column(server_default=true())

    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # This will help us to get the author of the post
    # Makes sure to add that to shema
    author: Mapped[User] = relationship(
        "User",
        back_populates="posts",
    )

    # One Post -> Many PostLikes
    likes: Mapped[list[PostLike]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )
