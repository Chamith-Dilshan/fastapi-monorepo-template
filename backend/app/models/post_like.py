from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.orm import mapped_column

from app.core.base import Base
from app.models.post import Post
from app.models.user import User

if TYPE_CHECKING:
    pass


class PostLike(Base):
    __tablename__ = "post_likes"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Many PostLikes -> One User
    user: Mapped[User] = relationship("User", back_populates="likes")
    # Many PostLikes -> One Post
    post: Mapped[Post] = relationship("Post", back_populates="likes")
