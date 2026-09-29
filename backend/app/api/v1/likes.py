from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from app.core.config import settings
from app.dependancies.database_dep import SessionDep
from app.dependancies.security_dep import get_current_user_dep
from app.models.user import User
from app.services.post_like_service import PostLikeService

router = APIRouter(
    tags=["Likes"],
    prefix=f"{settings.API_V1_PREFIX}/likes",
)

# Reusable alias
CurrentUser = Annotated[User, Depends(get_current_user_dep)]


@router.post(
    "/{post_id}/like",
    status_code=status.HTTP_200_OK,
)
async def toggle_like(post_id: UUID, db: SessionDep, current_user: CurrentUser):
    service = PostLikeService(db)
    response = await service.toggle_like(post_id=post_id, user_id=current_user.id)

    return {
        "liked": response,
        "post_id": post_id,
    }
