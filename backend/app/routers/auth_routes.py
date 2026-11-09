"""Register, sign in, sign out, and administrator user management."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from app import auth, db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=auth.MIN_PASSWORD_LENGTH, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class RoleRequest(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


def _public(user: dict) -> dict:
    return {
        "user_id": user["user_id"], "email": user["email"],
        "display_name": user["display_name"], "role": user["role"],
        "is_active": user.get("is_active", True),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> dict:
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)

    email = body.email.strip().lower()
    with db.get_engine().begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM app_user WHERE lower(email) = :e"), {"e": email}
        ).first()
        if exists:
            # Deliberately the same shape of error as a weak password, and no
            # statement that the address is taken: account enumeration through
            # the registration form is the usual way a user list leaks.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That account could not be created. If the address is already "
                "registered, sign in or ask an administrator.",
            )

        # Bootstrap: the very first account is an administrator, because
        # otherwise a fresh deployment has nobody who can promote anyone.
        first = conn.execute(text("SELECT count(*) FROM app_user")).scalar_one() == 0
        role = "admin" if first else "user"

        row = conn.execute(
            text("""
            INSERT INTO app_user (email, display_name, role, password_hash)
            VALUES (:e, :n, :r, :h)
            RETURNING user_id, email, display_name, role, is_active
            """),
            {"e": email, "n": body.display_name.strip(), "r": role,
             "h": auth.hash_password(body.password)},
        ).mappings().one()

    return {
        "user": _public(dict(row)),
        "note": "First account on a new deployment is created as administrator."
        if role == "admin" else None,
    }


@router.post("/login")
def login(body: LoginRequest, request: Request) -> dict:
    email = body.email.strip().lower()
    ip = auth.client_ip(request)

    if auth.too_many_failures(email, ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed sign-in attempts. Wait 15 minutes and try again.",
        )

    row = db.one(
        "SELECT user_id, email, display_name, role, password_hash, is_active "
        "FROM app_user WHERE lower(email) = :e", e=email,
    )

    if row is None:
        auth.verify_dummy()  # equalise timing so unknown accounts are not detectable
        ok = False
    else:
        ok = auth.verify_password(body.password, row["password_hash"]) and row["is_active"]

    with db.get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO login_attempt (email, source_ip, succeeded) "
                 "VALUES (:e, :ip, :s)"),
            {"e": email, "ip": ip, "s": ok},
        )

    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    token, expires, _ = auth.issue_token(row["user_id"], row["email"], row["role"])
    with db.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE app_user SET last_login_at = now() WHERE user_id = :u"),
            {"u": row["user_id"]},
        )

    return {
        "access_token": token, "token_type": "bearer",
        "expires_at": expires.isoformat(), "user": _public(dict(row)),
    }


@router.post("/logout")
def logout(user: auth.CurrentUser = Depends(auth.current_user)) -> dict:
    """Revoke this token server-side.

    Without this, signing out would only clear the browser's copy while the
    token stayed valid for the rest of its life.
    """
    with db.get_engine().begin() as conn:
        conn.execute(
            text("""
            INSERT INTO revoked_token (jti, user_id, expires_at)
            VALUES (:j, :u, :e) ON CONFLICT (jti) DO NOTHING
            """),
            {"j": user.jti, "u": user.user_id, "e": user.expires_at},
        )
        # Housekeeping: revocations are only needed until the token would have
        # expired anyway.
        conn.execute(text("DELETE FROM revoked_token WHERE expires_at < now()"))
    return {"signed_out": True}


@router.get("/me")
def me(user: auth.CurrentUser = Depends(auth.current_user)) -> dict:
    return {
        "user_id": user.user_id, "email": user.email,
        "display_name": user.display_name, "role": user.role,
        "session_expires_at": user.expires_at.isoformat(),
    }


# --- administrator ----------------------------------------------------------

@router.get("/users")
def list_users(_: auth.CurrentUser = Depends(auth.require_admin)) -> dict:
    rows = db.rows(
        "SELECT user_id, email, display_name, role, is_active, created_at, last_login_at "
        "FROM app_user ORDER BY created_at"
    )
    return {"count": len(rows), "users": rows}


@router.patch("/users/{user_id}/role")
def set_role(
    user_id: int, body: RoleRequest,
    admin: auth.CurrentUser = Depends(auth.require_admin),
) -> dict:
    if user_id == admin.user_id and body.role != "admin":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot remove your own administrator access. Ask another "
            "administrator, so a deployment can never be left with none.",
        )

    with db.get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT user_id, role FROM app_user WHERE user_id = :u"), {"u": user_id}
        ).mappings().first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user.")

        if row["role"] != body.role:
            conn.execute(
                text("UPDATE app_user SET role = :r WHERE user_id = :u"),
                {"r": body.role, "u": user_id},
            )
            conn.execute(
                text("""
                INSERT INTO role_change (target_user, actor_user, old_role, new_role)
                VALUES (:t, :a, :o, :n)
                """),
                {"t": user_id, "a": admin.user_id, "o": row["role"], "n": body.role},
            )

    return {"user_id": user_id, "role": body.role}


@router.patch("/users/{user_id}/active")
def set_active(
    user_id: int, active: bool,
    admin: auth.CurrentUser = Depends(auth.require_admin),
) -> dict:
    if user_id == admin.user_id and not active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account."
        )
    with db.get_engine().begin() as conn:
        updated = conn.execute(
            text("UPDATE app_user SET is_active = :a WHERE user_id = :u RETURNING user_id"),
            {"a": active, "u": user_id},
        ).first()
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user.")
    # Deactivation takes effect immediately without touching revoked_token:
    # current_user re-reads is_active from the database on every request, so an
    # already-issued token stops working on the next call.
    return {"user_id": user_id, "is_active": active}
