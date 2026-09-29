from app.custom_types.post_types import PostWithLikeData
from app.dtos.post_dto import PostResponse


def post_to_response(
    data: PostWithLikeData,
) -> PostResponse:

    post = data["post"]

    return PostResponse(
        id=post.id,
        author=post.author,
        title=post.title,
        content=post.content,
        published=post.published,
        like_count=data["like_count"],
        is_liked=data["is_liked"],
        created_at=post.created_at,
        updated_at=post.updated_at,
    )
