import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer(auto_error=False)


def sign(data: str):
    return hmac.new(settings().auth_secret.encode(), data.encode(), hashlib.sha256).hexdigest()


def token(subject: str, ttl: int = 8 * 3600):
    data = base64.urlsafe_b64encode(json.dumps({"sub": subject, "exp": int(time.time()) + ttl}).encode()).decode()
    return data + "." + sign(data)


def owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        data, signature = credentials.credentials.split(".")
        if not hmac.compare_digest(sign(data), signature):
            raise ValueError()
        decoded = json.loads(base64.urlsafe_b64decode(data))
        if decoded["exp"] <= time.time() or decoded["sub"] != settings().admin_username:
            raise ValueError()
        return decoded["sub"]
    except (AttributeError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Sign in required") from None
