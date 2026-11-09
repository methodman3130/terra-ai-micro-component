"""Authentication unit tests. No database or network required."""
import os

import pytest

os.environ.setdefault("TERRA_JWT_SECRET", "test-secret-at-least-thirty-two-characters")

from app import auth  # noqa: E402


def test_password_hash_is_salted_and_verifiable():
    a = auth.hash_password("a-long-enough-passphrase")
    b = auth.hash_password("a-long-enough-passphrase")
    assert a != b, "identical passwords must not produce identical hashes"
    assert auth.verify_password("a-long-enough-passphrase", a)
    assert auth.verify_password("a-long-enough-passphrase", b)


def test_wrong_password_is_rejected():
    stored = auth.hash_password("the-correct-passphrase")
    assert not auth.verify_password("the-incorrect-passphrase", stored)


def test_plaintext_never_appears_in_the_stored_hash():
    secret = "sup3rsecret-passphrase"
    assert secret not in auth.hash_password(secret)


def test_corrupt_hash_fails_closed_instead_of_raising():
    for bad in ["", "not-a-hash", "scrypt$x$y$z$a$b", "bcrypt$1$2$3$4$5"]:
        assert auth.verify_password("anything", bad) is False


def test_short_and_common_passwords_are_refused():
    assert auth.password_problem("short") is not None
    assert auth.password_problem("password") is not None
    assert auth.password_problem("a-perfectly-fine-passphrase") is None


def test_minimum_length_is_enforced_at_the_boundary():
    assert auth.password_problem("x" * (auth.MIN_PASSWORD_LENGTH - 1)) is not None
    assert auth.password_problem("x" * auth.MIN_PASSWORD_LENGTH) is None


def test_token_round_trips_with_role_and_expiry():
    import jwt

    token, expires, jti = auth.issue_token(7, "a@b.ph", "admin")
    claims = jwt.decode(token, os.environ["TERRA_JWT_SECRET"], algorithms=[auth.ALGORITHM])
    assert claims["sub"] == "7"
    assert claims["role"] == "admin"
    assert claims["jti"] == jti
    # PyJWT encodes datetimes as integer epoch seconds.
    assert claims["exp"] == int(expires.timestamp())
    assert claims["exp"] > claims["iat"]


def test_each_token_has_a_distinct_id_so_one_logout_cannot_revoke_another():
    _, _, a = auth.issue_token(1, "a@b.ph", "user")
    _, _, b = auth.issue_token(1, "a@b.ph", "user")
    assert a != b


def test_a_token_signed_with_another_key_is_rejected():
    import jwt

    token, _, _ = auth.issue_token(1, "a@b.ph", "admin")
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, "a-completely-different-signing-key-value", algorithms=[auth.ALGORITHM])


def test_missing_secret_refuses_to_issue_tokens(monkeypatch):
    """A default signing key would be the same as no authentication at all."""
    monkeypatch.delenv("TERRA_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="TERRA_JWT_SECRET"):
        auth.issue_token(1, "a@b.ph", "user")


def test_short_secret_is_refused(monkeypatch):
    monkeypatch.setenv("TERRA_JWT_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="at least 32"):
        auth.issue_token(1, "a@b.ph", "user")
