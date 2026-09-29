from app.core.config import settings

API_V1 = settings.API_V1_PREFIX

# Auth
REGISTER_URL = f"{API_V1}/auth/register"
LOGIN_URL = f"{API_V1}/auth/login"
ME_URL = f"{API_V1}/auth/me"

# Users
USERS_URL = f"{API_V1}/users"

# Posts
POSTS_URL = f"{API_V1}/posts"
PUBLIC_POSTS_URL = f"{API_V1}/posts/public"

# Likes
LIKES_URL = f"{API_V1}/likes"

# Shared test values
DEFAULT_PASSWORD = "StrongP@ssw0rd!"
INVALID_TOKEN = "Bearer invalid.jwt.token"
