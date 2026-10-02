"""Per-request context, readable without passing a `Request` everywhere.

Set by `RequestContextMiddleware` (see `app.core.middleware`) at the start of
every request. Read by the logging setup (to stamp every log line), the
exception handlers (to put the same id in the error envelope the client
sees), and the audit module (to link an audit row back to the request that
caused it).
"""

import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
current_user_id_var: ContextVar[str | None] = ContextVar(
    "current_user_id", default=None
)


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return request_id_var.get()
