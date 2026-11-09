"""Authentication: password hashing, tokens, and role checks.

Decisions worth knowing:

* **scrypt, from the standard library.** No bcrypt/passlib dependency to pin or
  patch. Parameters are stored in the hash string, so they can be raised later
  without invalidating existing accounts.
* **Tokens are revocable.** A JWT is otherwise valid until it expires, which
  would make "log out" a client-side fiction. Every request checks the token's
  jti against ``revoked_token``.
* **Sign-in failures are throttled** per email and per source address, so one
  attacker cannot lock out every account by guessing against it.
* **Timing.** An unknown email still runs a hash verification against a dummy,
  so response time does not reveal which addresses are registered.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import db

# --- password hashing -------------------------------------------------------

SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_LEN = 32

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=KEY_LEN, maxmem=64 * 1024 * 1024,
    )
    return "$".join([
        "scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
        base64.b64encode(salt).decode(), base64.b64encode(key).decode(),
    ])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        key = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(key_b64)),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(key, base64.b64decode(key_b64))
    except (ValueError, TypeError):
        return False


# A real hash to compare against when the email is unknown, so the failure path
# costs the same as the success path.
_DUMMY_HASH = hash_password("timing-equalisation-only-never-a-real-password")


def verify_dummy() -> None:
    verify_password("x", _DUMMY_HASH)


def password_problem(password: str) -> str | None:
    """Return why a password is unacceptable, or None if it is fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() in {"password", "passphrase", "123456789012", "qwertyuiop12"}:
        return "That password is too common."
    return None


# --- tokens -----------------------------------------------------------------

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=8)


def _secret() -> str:
    secret = os.environ.get("TERRA_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "TERRA_JWT_SECRET is not set. Generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
            "and put it in .env. The server will not start without it, because "
            "a default signing key is the same as no authentication at all."
        )
    if len(secret) < 32:
        raise RuntimeError("TERRA_JWT_SECRET must be at least 32 characters.")
    return secret


def issue_token(user_id: int, email: str, role: str) -> tuple[str, datetime, str]:
    now = datetime.now(timezone.utc)
    expires = now + TOKEN_TTL
    jti = str(uuid.uuid4())
    token = jwt.encode(
        {"sub": str(user_id), "email": email, "role": role,
         "iat": now, "exp": expires, "jti": jti},
        _secret(), algorithm=ALGORITHM,
    )
    return token, expires, jti


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    email: str
    display_name: str
    role: str
    jti: str
    expires_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if credentials is None:
        raise _CREDENTIALS_ERROR
    try:
        claims = jwt.decode(credentials.credentials, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired; sign in again.")
    except jwt.InvalidTokenError:
        raise _CREDENTIALS_ERROR

    jti = claims.get("jti")
    if not jti or db.one("SELECT jti FROM revoked_token WHERE jti = :j", j=jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been signed out.")

    # Role and active status are read from the database, not trusted from the
    # token: an admin demoted or an account disabled must take effect at once,
    # not whenever an eight-hour token happens to expire.
    row = db.one(
        "SELECT user_id, email, display_name, role, is_active FROM app_user WHERE user_id = :u",
        u=int(claims["sub"]),
    )
    if row is None or not row["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active.")

    return CurrentUser(
        user_id=row["user_id"], email=row["email"], display_name=row["display_name"],
        role=row["role"], jti=jti,
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
    )


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required.")
    return user


# --- throttling -------------------------------------------------------------

MAX_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


def too_many_failures(email: str, source_ip: str | None) -> bool:
    since = datetime.now(timezone.utc) - LOCKOUT_WINDOW
    row = db.one(
        """
        SELECT count(*) AS n FROM login_attempt
        -- Casts are explicit: PostgreSQL cannot infer a bare parameter's type in
        -- an "IS NOT NULL OR col = param" test and rejects the statement.
        -- (Note: never write a colon-prefixed name in these comments -
        -- SQLAlchemy scans comments too and would treat it as a bind parameter.)
        WHERE succeeded = FALSE AND attempted_at > CAST(:since AS TIMESTAMPTZ)
          AND (lower(email) = lower(CAST(:email AS TEXT))
               OR (CAST(:ip AS TEXT) IS NOT NULL AND source_ip = CAST(:ip AS TEXT)))
        """,
        since=since, email=email, ip=source_ip,
    )
    return bool(row and row["n"] >= MAX_FAILURES)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
