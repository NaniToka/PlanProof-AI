"""Automated unit and security tests for Supabase JWT verification and tenant identity."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from pydantic import SecretStr

from app.auth import (
    AuthenticatedUser,
    AuthenticationError,
    GuestUser,
    SupabaseTokenVerifier,
    extract_bearer_token,
    get_current_user,
    get_current_user_or_guest,
)
from app.config import ConfigurationError, Settings


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================

TEST_SECRET = "test-jwt-secret-with-sufficient-length-32-bytes!"


def create_token(
    payload: dict,
    secret_or_key: str | bytes = TEST_SECRET,
    algorithm: str = "HS256",
    headers: dict | None = None,
) -> str:
    """Helper to generate JWT tokens for testing."""
    return jwt.encode(payload, secret_or_key, algorithm=algorithm, headers=headers)


@pytest.fixture
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate in-memory RSA private/public keypair PEM bytes."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def make_request(headers: dict[str, str] | None = None) -> Request:
    """Create a mock Starlette/FastAPI request with given headers."""
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/events",
        "headers": raw_headers,
    }
    return Request(scope)


# ==============================================================================
# 1. Bearer Token Extraction Tests
# ==============================================================================


def test_extract_bearer_token_success() -> None:
    """Verify extraction of standard Bearer token."""
    req = make_request({"Authorization": "Bearer my.jwt.token"})
    token = extract_bearer_token(req)
    assert token == "my.jwt.token"


def test_extract_bearer_token_missing() -> None:
    """Verify missing Authorization header returns None."""
    req = make_request({})
    assert extract_bearer_token(req) is None


def test_extract_bearer_token_non_bearer_scheme() -> None:
    """Verify non-Bearer auth schemes are rejected."""
    req = make_request({"Authorization": "Basic dXNlcjpwYXNz"})
    with pytest.raises(AuthenticationError) as exc:
        extract_bearer_token(req)
    assert exc.value.code == "INVALID_TOKEN"
    assert "Bearer scheme" in exc.value.message


def test_extract_bearer_token_empty_token() -> None:
    """Verify empty Bearer token is rejected."""
    req = make_request({"Authorization": "Bearer   "})
    with pytest.raises(AuthenticationError) as exc:
        extract_bearer_token(req)
    assert exc.value.code == "INVALID_TOKEN"
    assert "cannot be empty" in exc.value.message


# ==============================================================================
# 2. Symmetric (HS256) JWT Verification Tests
# ==============================================================================


def test_verify_valid_hs256_token() -> None:
    """Verify that a valid Supabase HS256 token is verified and extracts claims."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "email": "host@planproof.ai",
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    user = verifier.verify_token(token)
    assert isinstance(user, AuthenticatedUser)
    assert user.user_id == user_id
    assert user.email == "host@planproof.ai"
    assert user.role == "authenticated"
    assert user.is_authenticated is True
    assert user.is_guest is False


def test_verify_expired_token_rejected() -> None:
    """Verify that expired tokens are rejected with TOKEN_EXPIRED."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) - timedelta(minutes=5)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_verify_invalid_signature_rejected() -> None:
    """Verify that tokens signed with a different key are rejected with INVALID_SIGNATURE."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key="wrong-secret-key-123456789012345")

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_SIGNATURE"


def test_verify_wrong_audience_rejected() -> None:
    """Verify that tokens with unexpected audience are rejected with INVALID_AUDIENCE."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "wrong-audience",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET), supabase_jwt_audience="authenticated")
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_AUDIENCE"


def test_verify_wrong_issuer_rejected() -> None:
    """Verify that tokens with unexpected issuer are rejected with INVALID_ISSUER."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": "https://attacker.com/auth/v1",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        supabase_url="https://valid-project.supabase.co",
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_ISSUER"


def test_verify_missing_sub_rejected() -> None:
    """Verify tokens without 'sub' claim are rejected."""
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_TOKEN"
    assert "missing" in exc.value.message.lower()


def test_verify_invalid_uuid_sub_rejected() -> None:
    """Verify tokens with non-UUID 'sub' claims are rejected."""
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": "not-a-valid-uuid",
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_TOKEN"
    assert "UUID" in exc.value.message


# ==============================================================================
# 3. Asymmetric (RS256) & JWKS Verification Tests
# ==============================================================================


def test_verify_valid_rs256_with_public_key(rsa_keypair: tuple[bytes, bytes]) -> None:
    """Verify RS256 token verification using PEM public key configuration."""
    priv_pem, pub_pem = rsa_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "email": "asymmetric@planproof.ai",
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=priv_pem, algorithm="RS256")

    settings = Settings(supabase_jwt_public_key=SecretStr(pub_pem.decode("utf-8")))
    verifier = SupabaseTokenVerifier(settings=settings)

    user = verifier.verify_token(token)
    assert user.user_id == user_id
    assert user.email == "asymmetric@planproof.ai"


def test_verify_valid_rs256_with_jwks_client(rsa_keypair: tuple[bytes, bytes]) -> None:
    """Verify RS256 token verification using mock PyJWKClient."""
    priv_pem, pub_pem = rsa_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=priv_pem, algorithm="RS256", headers={"kid": "key-1"})

    mock_signing_key = MagicMock()
    mock_signing_key.key = pub_pem.decode("utf-8")

    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

    settings = Settings(supabase_jwks_url="https://mock.supabase.co/auth/v1/.well-known/jwks.json")
    verifier = SupabaseTokenVerifier(settings=settings, jwks_client=mock_jwks)

    user = verifier.verify_token(token)
    assert user.user_id == user_id
    mock_jwks.get_signing_key_from_jwt.assert_called_once_with(token)


# ==============================================================================
# 4. Security & Algorithm Allowlist Tests
# ==============================================================================


def test_verify_unsigned_none_algorithm_rejected() -> None:
    """Verify unsigned tokens with 'none' algorithm are unconditionally rejected."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    # Create unsigned token
    token = jwt.encode(payload, key="", algorithm="none")

    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_ALGORITHM"
    assert "Unsigned tokens are strictly prohibited" in exc.value.message


def test_verify_disallowed_algorithm_rejected() -> None:
    """Verify tokens signed with algorithm not in allowlist are rejected."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=TEST_SECRET, algorithm="HS384")

    # Only HS256 allowed
    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        supabase_jwt_algorithms=["HS256"],
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_ALGORITHM"


def test_algorithm_pinning_rejects_unpinned_algorithms(rsa_keypair: tuple[bytes, bytes]) -> None:
    """Verify production operator can pin RS256 and reject HS256, or pin HS256 and reject RS256."""
    priv_pem, pub_pem = rsa_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    hs_token = create_token(payload, secret_or_key=TEST_SECRET, algorithm="HS256")
    rs_token = jwt.encode(payload, priv_pem, algorithm="RS256")

    # Case 1: Pinned to RS256 only (rejects HS256)
    rs_pinned_settings = Settings(
        supabase_jwt_algorithms=["RS256"],
        supabase_jwt_public_key=SecretStr(pub_pem.decode("utf-8")),
    )
    rs_verifier = SupabaseTokenVerifier(settings=rs_pinned_settings)
    with pytest.raises(AuthenticationError) as exc_hs:
        rs_verifier.verify_token(hs_token)
    assert exc_hs.value.code == "INVALID_ALGORITHM"
    # But validly verifies RS256
    user = rs_verifier.verify_token(rs_token)
    assert user.user_id == user_id

    # Case 2: Pinned to HS256 only (rejects RS256)
    hs_pinned_settings = Settings(
        supabase_jwt_algorithms=["HS256"],
        supabase_jwt_secret=SecretStr(TEST_SECRET),
    )
    hs_verifier = SupabaseTokenVerifier(settings=hs_pinned_settings)
    with pytest.raises(AuthenticationError) as exc_rs:
        hs_verifier.verify_token(rs_token)
    assert exc_rs.value.code == "INVALID_ALGORITHM"
    # But validly verifies HS256
    user_hs = hs_verifier.verify_token(hs_token)
    assert user_hs.user_id == user_id


def test_missing_secret_fails_closed() -> None:
    """Verify that if SUPABASE_JWT_SECRET is missing, verifier fails closed rather than treating token as valid."""
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload)

    # No secret configured
    settings = Settings(supabase_jwt_secret=None)
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "AUTH_NOT_CONFIGURED"


# ==============================================================================
# 5. FastAPI Dependency Policy Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_get_current_user_requires_token() -> None:
    """Verify get_current_user rejects requests without token."""
    req = make_request({})
    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        await get_current_user(req, verifier=verifier)
    assert exc.value.code == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_get_current_user_or_guest_allows_guest_in_memory() -> None:
    """Verify guest access is permitted in memory mode when no auth header is sent."""
    req = make_request({})
    settings = Settings(storage_backend="memory", app_env="development")
    verifier = SupabaseTokenVerifier(settings=settings)

    user = await get_current_user_or_guest(req, verifier=verifier, settings=settings)
    assert isinstance(user, GuestUser)
    assert user.is_authenticated is False
    assert user.is_guest is True
    assert isinstance(user.user_id, UUID)


@pytest.mark.asyncio
async def test_get_current_user_or_guest_rejects_guest_when_postgres_active() -> None:
    """Verify unauthenticated requests are rejected with 401 when storage_backend is postgres."""
    req = make_request({})
    settings = Settings(storage_backend="postgres", app_env="development")
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        await get_current_user_or_guest(req, verifier=verifier, settings=settings)
    assert exc.value.code == "AUTHENTICATION_REQUIRED"
    assert "PostgreSQL" in exc.value.message


@pytest.mark.asyncio
async def test_get_current_user_or_guest_rejects_guest_in_production_when_disabled() -> None:
    """Verify unauthenticated requests are rejected in production when allow_guest_mode is False."""
    req = make_request({})
    settings = Settings(storage_backend="memory", app_env="production", allow_guest_mode=False)
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        await get_current_user_or_guest(req, verifier=verifier, settings=settings)
    assert exc.value.code == "AUTHENTICATION_REQUIRED"
    assert "production" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_get_current_user_or_guest_strict_when_token_provided() -> None:
    """Verify that if an auth header is provided, it is strictly validated even in dev mode."""
    req = make_request({"Authorization": "Bearer invalid.fake.token"})
    settings = Settings(storage_backend="memory", app_env="development", supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        await get_current_user_or_guest(req, verifier=verifier, settings=settings)
    assert exc.value.code in ("INVALID_TOKEN", "INVALID_ALGORITHM")


def test_user_repr_does_not_leak_sensitive_claims() -> None:
    """Verify repr of AuthenticatedUser masks raw claims and email."""
    user = AuthenticatedUser(
        user_id=uuid4(),
        email="sensitive-email@secret.com",
        role="authenticated",
        claims={"token": "secret-jwt", "password_hash": "12345"},
    )
    user_repr = repr(user)
    assert "secret-jwt" not in user_repr
    assert "password_hash" not in user_repr
    assert "sensitive-email@secret.com" not in user_repr


@pytest.mark.asyncio
async def test_invalid_bearer_with_valid_guest_token_fails_closed() -> None:
    """Verify an invalid Bearer token fails with 401 even if a valid guest token is also supplied."""
    from app.auth import create_guest_session_token

    valid_guest_token, _, _ = create_guest_session_token(secret=TEST_SECRET)
    req = make_request({
        "Authorization": "Bearer invalid.fake.token",
        "X-Guest-Session-ID": valid_guest_token,
    })
    settings = Settings(
        storage_backend="memory",
        app_env="development",
        supabase_jwt_secret=SecretStr(TEST_SECRET),
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        await get_current_user_or_guest(req, verifier=verifier, settings=settings)
    assert exc.value.code in ("INVALID_TOKEN", "INVALID_ALGORITHM")


def test_jwks_connection_failure_distinguished_as_service_unavailable() -> None:
    """Verify that network outages talking to JWKS endpoint return AUTH_PROVIDER_UNAVAILABLE with status 503."""
    import base64
    import json
    from jwt import PyJWKClientConnectionError

    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_jwt_algorithms=["RS256"],
    )
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.side_effect = PyJWKClientConnectionError(
        "Connection timed out reaching example.supabase.co"
    )
    verifier = SupabaseTokenVerifier(settings=settings, jwks_client=mock_jwks)

    h = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"sub": str(uuid4()), "exp": 9999999999}).encode()).decode().rstrip("=")
    token = f"{h}.{p}.fakesig"

    with pytest.raises(AuthenticationError) as exc_info:
        verifier.verify_token(token)

    assert exc_info.value.code == "AUTH_PROVIDER_UNAVAILABLE"
    assert exc_info.value.status_code == 503


# ==============================================================================
# 6. Key-Type Binding & Asymmetric Algorithm Confusion Security Tests
# ==============================================================================


@pytest.fixture
def ec_keypair() -> tuple[bytes, bytes]:
    """Generate in-memory ECDSA (SECP256R1) private/public keypair PEM bytes."""
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def test_verify_valid_es256_with_ec_public_key(ec_keypair: tuple[bytes, bytes]) -> None:
    """Verify ES256 ECDSA token verification using PEM public key configuration."""
    priv_pem, pub_pem = ec_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "email": "ecdsa@planproof.ai",
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=priv_pem, algorithm="ES256")

    settings = Settings(supabase_jwt_public_key=SecretStr(pub_pem.decode("utf-8")))
    verifier = SupabaseTokenVerifier(settings=settings)

    user = verifier.verify_token(token)
    assert user.user_id == user_id
    assert user.email == "ecdsa@planproof.ai"


def test_verify_wrong_key_type_rsa_configured_with_ec_token(
    rsa_keypair: tuple[bytes, bytes], ec_keypair: tuple[bytes, bytes]
) -> None:
    """Verify token signed with ES256 is rejected when server is configured with RSA key."""
    ec_priv, _ = ec_keypair
    _, rsa_pub = rsa_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=ec_priv, algorithm="ES256")

    settings = Settings(
        supabase_jwt_public_key=SecretStr(rsa_pub.decode("utf-8")),
        supabase_jwt_algorithms=["RS256", "ES256"],
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_KEY_TYPE"
    assert "EC public key" in exc.value.message


def test_verify_wrong_key_type_ec_configured_with_rsa_token(
    rsa_keypair: tuple[bytes, bytes], ec_keypair: tuple[bytes, bytes]
) -> None:
    """Verify token signed with RS256 is rejected when server is configured with EC key."""
    rsa_priv, _ = rsa_keypair
    _, ec_pub = ec_keypair
    user_id = uuid4()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
    }
    token = create_token(payload, secret_or_key=rsa_priv, algorithm="RS256")

    settings = Settings(
        supabase_jwt_public_key=SecretStr(ec_pub.decode("utf-8")),
        supabase_jwt_algorithms=["RS256", "ES256"],
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_KEY_TYPE"
    assert "RSA public key" in exc.value.message


def test_verify_algorithm_confusion_hs256_with_asymmetric_key(
    rsa_keypair: tuple[bytes, bytes],
) -> None:
    """Verify that an asymmetric key configured in SUPABASE_JWT_SECRET is rejected for HMAC."""
    _, pub_pem = rsa_keypair
    settings = Settings(supabase_jwt_secret=SecretStr(pub_pem.decode("utf-8")))
    verifier = SupabaseTokenVerifier(settings=settings)

    token = create_token({"sub": str(uuid4()), "exp": 9999999999, "aud": "authenticated"})
    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_KEY_TYPE"
    assert "Asymmetric key cannot be used for symmetric HMAC" in exc.value.message


def test_verify_jwks_wrong_key_type_rejected(rsa_keypair: tuple[bytes, bytes], ec_keypair: tuple[bytes, bytes]) -> None:
    """Verify that if JWKS returns an EC key for an RS256 token, it is rejected with INVALID_KEY_TYPE."""
    rsa_priv, _ = rsa_keypair
    _, ec_pub = ec_keypair
    user_id = uuid4()
    token = create_token({"sub": str(user_id), "exp": 9999999999, "aud": "authenticated"}, secret_or_key=rsa_priv, algorithm="RS256")

    mock_signing_key = MagicMock()
    # Mock returns EC key instead of RSA key
    mock_signing_key.key = ec_pub.decode("utf-8")
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

    settings = Settings(supabase_jwks_url="https://mock.supabase.co/jwks.json", supabase_jwt_algorithms=["RS256"])
    verifier = SupabaseTokenVerifier(settings=settings, jwks_client=mock_jwks)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_KEY_TYPE"


def test_verify_missing_required_claims_aud_and_iss() -> None:
    """Verify that missing aud or iss claims are rejected when configured in settings."""
    user_id = uuid4()
    token_no_aud = create_token({"sub": str(user_id), "exp": 9999999999})

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://my.supabase.co/auth/v1",
    )
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token(token_no_aud)
    assert exc.value.code == "INVALID_TOKEN"
    assert "missing" in exc.value.message.lower()


def test_verify_malformed_token_payload_fails_closed() -> None:
    """Verify that corrupt base64 payload fails closed with 401 INVALID_TOKEN."""
    settings = Settings(supabase_jwt_secret=SecretStr(TEST_SECRET))
    verifier = SupabaseTokenVerifier(settings=settings)

    with pytest.raises(AuthenticationError) as exc:
        verifier.verify_token("eyJhbGciOiJIUzI1NiJ9.corrupt!!!payload.fakesig")
    assert exc.value.code == "INVALID_TOKEN"


# ==============================================================================
# 7. Guest Signing Secret Lifecycle Tests
# ==============================================================================


def test_guest_signing_secret_validation_in_production() -> None:
    """Verify production fails fast if guest sessions are enabled without GUEST_SESSION_SECRET."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        Settings(app_env="production", allow_guest_mode=True, guest_session_secret=None)
    assert "GUEST_SESSION_SECRET" in str(exc.value)


def test_guest_signing_secret_too_short_rejected() -> None:
    """Verify secrets shorter than 32 characters are rejected."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        Settings(guest_session_secret=SecretStr("short-secret-under-32-chars"))
    assert "at least 32 characters" in str(exc.value)


def test_guest_secret_fallback_forbidden_in_production_and_postgres() -> None:
    """Calling get_guest_session_secret_bytes in production/postgres without secret raises ConfigurationError."""
    from app.config import ConfigurationError

    # Production with guest mode False (so Settings instantiates) but no guest secret
    prod_settings = Settings(app_env="production", allow_guest_mode=False, guest_session_secret=None)
    with pytest.raises(ConfigurationError):
        prod_settings.get_guest_session_secret_bytes()

    # PostgreSQL storage backend without guest secret
    pg_settings = Settings(storage_backend="postgres", guest_session_secret=None)
    with pytest.raises(ConfigurationError):
        pg_settings.get_guest_session_secret_bytes()


def test_create_and_verify_guest_token_rejects_insufficient_secret() -> None:
    """create_guest_session_token and verify_guest_session_token reject empty or too-short secrets."""
    from app.auth import create_guest_session_token, verify_guest_session_token

    with pytest.raises(AuthenticationError) as exc:
        create_guest_session_token(secret="too-short")
    assert exc.value.code == "INVALID_GUEST_SESSION"

    with pytest.raises(AuthenticationError) as exc:
        verify_guest_session_token("gst.fake.token", secret="too-short")
    assert exc.value.code == "INVALID_GUEST_SESSION"


