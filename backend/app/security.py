"""Password hashing and JWT creation/verification. Pure functions plus one small stateful
helper (the dummy hash used to equalize login timing) — no database or network I/O, so this
is independently testable with synthetic inputs.

Refresh tokens are handled here too: a refresh token is a 256-bit random value the caller
sees once; only its SHA-256 hash is ever stored (app/routers/auth.py), so a leaked database
does not hand out working tokens.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()
# A real hash of an unusable password, computed once. Verifying against this on a "user not
# found" login takes about as long as a real verify, so the response time doesn't reveal
# whether an email is registered.
_DUMMY_HASH = _hasher.hash(secrets.token_hex(32))

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "vero.ai"
JWT_AUDIENCE = "vero.ai-api"

ACCESS_TOKEN_TYPE = "access"


class TokenError(ValueError):
    """An access token is missing, malformed, expired, or signed with the wrong key/algorithm."""


# -- passwords -------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """True if `password` matches `password_hash`. `password_hash=None` (no such user)
    still does a real Argon2 verify against a dummy hash, so the two cases take the same
    time and a timing attack can't be used to enumerate registered emails."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except VerifyMismatchError:
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """True if `password_hash` was made with weaker parameters than we'd use today (e.g.
    after an upgrade) — checked on a successful login so hashes improve over time."""
    return _hasher.check_needs_rehash(password_hash)


# -- access tokens (JWT) -----------------------------------------------------------------


def create_access_token(user_id: uuid.UUID, ttl_seconds: int, secret_key: str, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        # A registered-but-unchecked claim (RFC 7519): its only job is to make each token
        # unique even when issued for the same user in the same second, since `exp`/`iat`
        # are encoded as whole-second NumericDate values and would otherwise collide.
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> uuid.UUID:
    """Returns the user id, or raises TokenError. `algorithms` is fixed to exactly one
    value: without it PyJWT would accept whatever algorithm the token itself claims,
    which is how "alg: none" / algorithm-confusion forgeries work."""
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenError("Not an access token")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("Malformed subject claim") from exc


# -- refresh tokens (opaque, hashed at rest) ----------------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_tokens_match(token: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_refresh_token(token), stored_hash)
