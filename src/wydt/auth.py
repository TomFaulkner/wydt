import os
import hashlib
from functools import wraps
from flask import request, Response


def _get_password_hash():
    password = os.getenv("WYDT_PASSWORD")
    if not password:
        return None
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str) -> bool:
    stored_hash = _get_password_hash()
    if not stored_hash:
        return True
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


def check_auth():
    auth = request.authorization
    if not auth:
        return False
    return _verify_password(auth.password)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not check_auth():
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="WYDT"'},
            )
        return f(*args, **kwargs)

    return decorated
