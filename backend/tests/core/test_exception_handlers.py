"""Every error path through register_exception_handlers, on a throwaway app
so each one can be triggered deliberately."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import (
    ConflictException,
    DatabaseException,
    ForbiddenException,
    InvalidOTPException,
    NotFoundException,
    ValidationException,
)


class Body(BaseModel):
    count: int


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def not_found():
        raise NotFoundException(message="Thing missing", details={"id": 7})

    @app.get("/conflict")
    async def conflict():
        raise ConflictException(message="Already there")

    @app.get("/forbidden")
    async def forbidden():
        raise ForbiddenException(message="No")

    @app.get("/validation")
    async def validation():
        raise ValidationException(message="Bad shape")

    @app.get("/otp")
    async def otp():
        raise InvalidOTPException()

    @app.get("/db")
    async def db():
        raise DatabaseException()

    @app.get("/http-401")
    async def http_401():
        raise HTTPException(
            status_code=401, detail="Nope", headers={"WWW-Authenticate": "Bearer"}
        )

    @app.get("/http-418")
    async def http_418():
        raise HTTPException(status_code=418, detail="Teapot")

    @app.get("/sqlalchemy")
    async def sqlalchemy():
        raise SQLAlchemyError("SELECT secret FROM table -- internal detail")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("internal detail that must not leak")

    @app.post("/body")
    async def body(payload: Body):
        return payload

    return app


@pytest_asyncio.fixture
async def http():
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/not-found", 404, "not_found"),
        ("/conflict", 409, "conflict"),
        ("/forbidden", 403, "forbidden"),
        ("/validation", 422, "validation_error"),
        ("/otp", 400, "invalid_otp"),
        ("/db", 500, "database_error"),
    ],
)
async def test_app_exceptions_use_their_own_status_and_code(http, path, status, code):
    response = await http.get(path)
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert set(error) == {"code", "message", "details", "request_id"}


@pytest.mark.asyncio
async def test_details_are_passed_through(http):
    response = await http.get("/not-found")
    assert response.json()["error"]["details"] == {"id": 7}


@pytest.mark.asyncio
async def test_request_validation_errors_list_the_failing_fields(http):
    response = await http.post("/body", json={"count": "not-a-number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    fields = error["details"]["field_errors"]
    assert fields[0]["loc"] == ["body", "count"]


@pytest.mark.asyncio
async def test_plain_http_exception_is_wrapped_and_keeps_its_headers(http):
    response = await http.get("/http-401")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.json()["error"]["message"] == "Nope"


@pytest.mark.asyncio
async def test_unmapped_http_status_falls_back_to_a_generic_code(http):
    response = await http.get("/http-418")
    assert response.status_code == 418
    assert response.json()["error"]["code"] == "http_error"


@pytest.mark.asyncio
async def test_unknown_route_is_wrapped_too(http):
    response = await http.get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_leaked_database_errors_never_expose_their_message(http):
    response = await http.get("/sqlalchemy")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "database_error"
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_unhandled_exceptions_become_a_generic_500(http):
    response = await http.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "internal detail" not in response.text
