from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError as JoseJWTError, jwt

ALGORITHM = "HS256"


def create_token(user_id: str, username: str, secret: str, role: str = "read", expires_hours: int = 24) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": exp,
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, secret: str) -> dict | None:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JoseJWTError:
        return None
