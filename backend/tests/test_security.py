"""Password hashing and JWT creation/verification. Pure functions — no database, no
network — tested with synthetic inputs and, where relevant, real forged tokens."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    refresh_tokens_match,
    verify_password,
)

SECRET = "x" * 32


class TestPasswordHashing:
    def test_a_correct_password_verifies(self):
        assert verify_password("hunter2", hash_password("hunter2")) is True

    def test_a_wrong_password_does_not_verify(self):
        assert verify_password("wrong", hash_password("hunter2")) is False

    def test_the_stored_hash_never_contains_the_plaintext_password(self):
        assert "hunter2" not in hash_password("hunter2")

    def test_hashing_the_same_password_twice_gives_different_hashes(self):
        # Argon2 salts each hash independently, so two users with the same password never
        # have matching rows in the database.
        assert hash_password("hunter2") != hash_password("hunter2")

    def test_a_none_hash_does_a_real_verify_and_fails(self):
        # The "no such user" path: still does real Argon2 work, just against a dummy hash.
        assert verify_password("anything", None) is False

    def test_a_none_hash_and_a_real_hash_take_about_the_same_time(self):
        real_hash = hash_password("hunter2")

        start = time.perf_counter()
        verify_password("wrong-but-real-user", real_hash)
        real_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        verify_password("anything", None)
        none_elapsed = time.perf_counter() - start

        # Generous bound (this is about order-of-magnitude, not exact parity) — a timing
        # side-channel would show up as one path being many times faster than the other.
        assert none_elapsed > real_elapsed * 0.3

    def test_a_freshly_hashed_password_does_not_need_rehashing(self):
        assert needs_rehash(hash_password("hunter2")) is False

    def test_an_empty_password_can_be_hashed_and_verified(self):
        # Length limits belong to the API schema (auth_schemas.py), not this layer.
        assert verify_password("", hash_password("")) is True


class TestAccessTokens:
    def test_a_fresh_token_decodes_to_the_user_id_it_was_created_for(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, ttl_seconds=900, secret_key=SECRET)

        assert decode_access_token(token, SECRET) == user_id

    def test_an_expired_token_is_rejected(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id, ttl_seconds=60, secret_key=SECRET, now=datetime.now(timezone.utc) - timedelta(hours=1)
        )

        with pytest.raises(TokenError):
            decode_access_token(token, SECRET)

    def test_a_token_signed_with_a_different_secret_is_rejected(self):
        token = create_access_token(uuid.uuid4(), ttl_seconds=900, secret_key=SECRET)

        with pytest.raises(TokenError):
            decode_access_token(token, "y" * 32)

    def test_a_tampered_payload_is_rejected(self):
        token = create_access_token(uuid.uuid4(), ttl_seconds=900, secret_key=SECRET)
        header, payload, signature = token.split(".")
        forged_payload = jwt.utils.base64url_encode(b'{"sub": "not-even-json-matching"}').decode()

        with pytest.raises(TokenError):
            decode_access_token(f"{header}.{forged_payload}.{signature}", SECRET)

    def test_garbage_is_rejected(self):
        with pytest.raises(TokenError):
            decode_access_token("not-a-jwt-at-all", SECRET)

    def test_alg_none_forgery_is_rejected(self):
        # The classic JWT forgery: claim there is no signature at all. decode_access_token
        # must refuse this outright, not just fail to verify a (nonexistent) signature.
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
            },
            key="",
            algorithm="none",
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    def test_a_token_signed_with_a_different_algorithm_is_rejected(self):
        # HS256 forged as HS512 with the same secret must not be accepted: algorithms is
        # pinned to exactly one value, not "whatever the token claims".
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
            },
            key=SECRET,
            algorithm="HS512",
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    def test_a_token_with_the_wrong_audience_is_rejected(self):
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": JWT_ISSUER,
                "aud": "someone-elses-api",
            },
            key=SECRET,
            algorithm=JWT_ALGORITHM,
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    def test_a_token_with_the_wrong_issuer_is_rejected(self):
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": "someone-else",
                "aud": JWT_AUDIENCE,
            },
            key=SECRET,
            algorithm=JWT_ALGORITHM,
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    @pytest.mark.parametrize("missing", ["exp", "iat", "sub", "type"])
    def test_a_token_missing_a_required_claim_is_rejected(self, missing):
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        }
        del payload[missing]
        forged = jwt.encode(payload, key=SECRET, algorithm=JWT_ALGORITHM)

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    def test_a_refresh_token_presented_as_an_access_token_is_rejected(self):
        # `type` really is checked, not just carried along for decoration.
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "refresh",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
            },
            key=SECRET,
            algorithm=JWT_ALGORITHM,
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)

    def test_two_tokens_for_the_same_user_at_the_same_instant_still_differ(self):
        # exp/iat are whole-second JWT NumericDate values, so without something else to
        # vary, two tokens issued in the same second for the same user would be identical.
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        first = create_access_token(user_id, ttl_seconds=900, secret_key=SECRET, now=now)
        second = create_access_token(user_id, ttl_seconds=900, secret_key=SECRET, now=now)

        assert first != second
        assert decode_access_token(first, SECRET) == decode_access_token(second, SECRET) == user_id

    def test_a_malformed_subject_is_rejected(self):
        forged = jwt.encode(
            {
                "sub": "not-a-uuid",
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
            },
            key=SECRET,
            algorithm=JWT_ALGORITHM,
        )

        with pytest.raises(TokenError):
            decode_access_token(forged, SECRET)


class TestRefreshTokens:
    def test_two_generated_tokens_are_different(self):
        assert generate_refresh_token() != generate_refresh_token()

    def test_a_generated_token_has_at_least_32_url_safe_characters(self):
        token = generate_refresh_token()
        assert len(token) >= 32
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_hashing_is_deterministic(self):
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_the_hash_never_contains_the_original_token(self):
        token = generate_refresh_token()
        assert token not in hash_refresh_token(token)

    def test_matching_and_non_matching_tokens(self):
        token = generate_refresh_token()
        stored_hash = hash_refresh_token(token)

        assert refresh_tokens_match(token, stored_hash) is True
        assert refresh_tokens_match(generate_refresh_token(), stored_hash) is False
