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


# Who is calling, as far as the server can tell — set per request by
# RequestContextMiddleware and read by `record_audit_event`, so no service has
# to be handed a Request just to say where an action came from. Behind a
# reverse proxy `client_ip` is only the real client if the proxy's forwarded
# headers are trusted (see FORWARDED_ALLOW_IPS in docker-compose.traefik.yml).
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)

# audit_logs.user_agent is VARCHAR(512); clients can send far more than that.
# The limit is applied where the column lives — record_audit_event — and only there.
USER_AGENT_MAX_LENGTH = 512


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return request_id_var.get()
