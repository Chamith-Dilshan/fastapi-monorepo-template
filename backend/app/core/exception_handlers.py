from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.core.exceptions import DatabaseException
from app.core.exceptions import (
    PostNotFoundError,
    PostOwnershipError,
)


def register_exception_handlers(
    app: FastAPI,
) -> None:

    @app.exception_handler(PostNotFoundError)
    async def post_not_found_handler(
        request,
        exc,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "message": "Post not found",
            },
        )

    @app.exception_handler(PostOwnershipError)
    async def post_owner_handler(
        request,
        exc,
    ):
        return JSONResponse(
            status_code=403,
            content={
                "message": "You are not the author of this post",
            },
        )

    @app.exception_handler(AppException)
    async def app_exception_handler(
            request: Request,
            exc: AppException,
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "message": exc.message,
            },
        )

    @app.exception_handler(DatabaseException)
    async def database_exception_handler(
            request: Request,
            exc: DatabaseException,
    ):
        return JSONResponse(
            status_code=500,
            content={
                "message": "Database error",
            },
        )