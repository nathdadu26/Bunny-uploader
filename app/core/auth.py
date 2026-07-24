from itsdangerous import URLSafeTimedSerializer, BadSignature
from fastapi import Request
from app.config import settings

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)
COOKIE_NAME = "dashboard_session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def create_session_cookie_value() -> str:
    return _serializer.dumps({"user": settings.DASHBOARD_USERNAME})


def is_logged_in(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=MAX_AGE_SECONDS)
        return True
    except BadSignature:
        return False
