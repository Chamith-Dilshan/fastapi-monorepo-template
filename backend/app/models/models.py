# keep these models imported here so their metadata is registered before
# Base.metadata.create_all()/Alembic autogenerate sees them — nothing here
# is used directly, hence the noqa's.
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.oauth_account import OAuthAccount  # noqa: F401
from app.models.otp_code import OTPCode  # noqa: F401
from app.models.user import User  # noqa: F401
