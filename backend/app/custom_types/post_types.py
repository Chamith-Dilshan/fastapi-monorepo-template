from typing import TypedDict

from app.models.post import Post


class PostWithLikeData(TypedDict):
    post: Post
    like_count: int
    is_liked: bool
