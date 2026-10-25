"""Supabase JWT Authentication, token verification, and tenant identity.

Provides:
- Cryptographic verification of Supabase-issued access tokens (HS256, RS256, ES256).
- Symmetric secret verification and asymmetric JWKS/PEM public key verification with key caching.
- Strict claim validation: sub (UUID), exp, aud, and optional iss.
- Explicit algorithm allowlist, strictly rejecting unsigned tokens ('none').
- Environment-aware guest vs. authenticated access policy.
- FastAPI dependencies: get_current_user and get_current_user_or_guest.
- Safe logging preserving credentials, secrets, and raw tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, Request
from jwt import PyJWKClient, PyJWKClientConnectionError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Domain Exceptions
# ==============================================================================


class AuthenticationError(Exception):
    """Raised when request authentication fails."""

    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ==============================================================================
# 2. User Domain Models
# ==============================================================================


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents a verified, authenticated Supabase user."""

    user_id: UUID
    email: str | None = None
    role: str = "authenticated"
    claims: dict[str, Any] = field(default_factory=dict)
    is_authenticated: bool = True
    is_guest: bool = False

    def __repr__(self) -> str:
        # Prevent token claims or email from leaking in sensitive logs
        return f"AuthenticatedUser(user_id={self.user_id}, role={self.role})"


@dataclass(frozen=True)
class GuestUser:
    """Represents an unauthenticated guest session (in-memory demo/development only)."""

    user_id: UUID | None = None
    is_authenticated: bool = False
    is_guest: bool = True

    def __repr__(self) -> str:
        return "GuestUser(is_guest=True)"


# ==============================================================================
# 3. Supabase Token Verifier
# ==============================================================================


class SupabaseTokenVerifier:
    """Verifies Supabase JWT access tokens securely using symmetric or asymmetric keys."""

    def __init__(
        self,
        settings: Settings,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self.settings = settings
        self.allowed_algorithms: list[str] = (
            [settings.supabase_jwt_algorithms]
            if isinstance(settings.supabase_jwt_algorithms, str)
            else list(settings.supabase_jwt_algorithms)
        )
        self._jwks_client = jwks_client
        if self._jwks_client is None and self.settings.resolved_jwks_url:
            self._jwks_client = PyJWKClient(
                self.settings.resolved_jwks_url,
                cache_keys=True,
                lifespan=300,
            )

    @staticmethod
    def _ensure_rsa_public_key(raw_key: Any) -> rsa.RSAPublicKey:
        """Ensure the provided key is or parses to an RSA public key."""
        if isinstance(raw_key, rsa.RSAPublicKey):
            return raw_key
        if isinstance(raw_key, (str, bytes)):
            pem_bytes = raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key
            try:
                loaded = serialization.load_pem_public_key(pem_bytes)
                if isinstance(loaded, rsa.RSAPublicKey):
                    return loaded
            except Exception:
                pass
        raise AuthenticationError(
            "INVALID_KEY_TYPE",
            "Algorithm requires an RSA public key, but an incompatible key type was provided.",
            status_code=401,
        )

    @staticmethod
    def _ensure_ec_public_key(raw_key: Any) -> ec.EllipticCurvePublicKey:
        """Ensure the provided key is or parses to an EC public key."""
        if isinstance(raw_key, ec.EllipticCurvePublicKey):
            return raw_key
        if isinstance(raw_key, (str, bytes)):
            pem_bytes = raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key
            try:
                loaded = serialization.load_pem_public_key(pem_bytes)
                if isinstance(loaded, ec.EllipticCurvePublicKey):
                    return loaded
            except Exception:
                pass
        raise AuthenticationError(
            "INVALID_KEY_TYPE",
            "Algorithm requires an EC public key, but an incompatible key type was provided.",
            status_code=401,
        )

    def verify_token(self, token: str) -> AuthenticatedUser:
        """Verify token signature, expiry, audience, issuer, and sub claim.

        Args:
            token: Raw Bearer token string.

        Returns:
            AuthenticatedUser with validated user UUID and claims.

        Raises:
            AuthenticationError: On verification failure, expiry, or invalid claims.
        """
        if not token or not isinstance(token, str) or not token.strip():
            raise AuthenticationError("INVALID_TOKEN", "Bearer token cannot be empty.")

        token = token.strip()

        # 1. Parse unverified header to inspect alg
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            logger.warning("Rejected malformed JWT header: %s", type(exc).__name__)
            raise AuthenticationError("INVALID_TOKEN", "Malformed token header.") from exc

        alg = unverified_header.get("alg")
        if not alg or not isinstance(alg, str):
            raise AuthenticationError("INVALID_ALGORITHM", "Missing token algorithm.")

        normalized_alg = alg.upper()

        # Reject unsigned tokens unconditionally
        if normalized_alg == "NONE":
            logger.warning("Rejected token with forbidden unsigned 'none' algorithm.")
            raise AuthenticationError(
                "INVALID_ALGORITHM", "Unsigned tokens are strictly prohibited."
            )

        # Enforce explicit allowlist
        if normalized_alg not in self.allowed_algorithms:
            logger.warning("Rejected token with disallowed algorithm: %s", normalized_alg)
            raise AuthenticationError(
                "INVALID_ALGORITHM",
                f"Algorithm '{normalized_alg}' is not in the allowed algorithms list.",
            )

        # 2. Resolve verification key based on algorithm with strict key-type binding
        key: Any = None
        if normalized_alg.startswith("HS"):
            jwt_secret = self.settings.get_supabase_jwt_secret_value()
            if not jwt_secret:
                logger.error("HS token received but SUPABASE_JWT_SECRET is not configured.")
                raise AuthenticationError(
                    "AUTH_NOT_CONFIGURED",
                    "Authentication verification credentials are not configured on the server.",
                    status_code=401,
                )
            # Ensure asymmetric PEM key cannot be used as HMAC secret (algorithm confusion protection)
            if jwt_secret.strip().startswith("-----BEGIN"):
                logger.error("Asymmetric key detected in SUPABASE_JWT_SECRET; cannot be used for HMAC.")
                raise AuthenticationError(
                    "INVALID_KEY_TYPE",
                    "Asymmetric key cannot be used for symmetric HMAC algorithm.",
                    status_code=401,
                )
            key = jwt_secret
        elif normalized_alg.startswith("RS"):
            raw_key: Any = None
            if self.settings.supabase_jwt_public_key:
                raw_key = self.settings.get_supabase_jwt_public_key_value()
            elif self._jwks_client:
                try:
                    signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                    raw_key = signing_key.key
                except (PyJWKClientConnectionError, urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                    logger.error("Failed to connect to JWKS endpoint: %s", exc)
                    raise AuthenticationError(
                        "AUTH_PROVIDER_UNAVAILABLE",
                        "Authentication service is temporarily unavailable. Please retry shortly.",
                        status_code=503,
                    ) from exc
                except Exception as exc:
                    logger.warning("Failed to obtain JWKS signing key: %s", type(exc).__name__)
                    raise AuthenticationError(
                        "INVALID_SIGNATURE",
                        "Unable to retrieve signing key for token.",
                        status_code=401,
                    ) from exc
            else:
                logger.error("RS token received but neither public key nor JWKS is configured.")
                raise AuthenticationError(
                    "AUTH_NOT_CONFIGURED",
                    "Asymmetric verification credentials are not configured on the server.",
                    status_code=401,
                )
            key = self._ensure_rsa_public_key(raw_key)
        elif normalized_alg.startswith("ES"):
            raw_key = None
            if self.settings.supabase_jwt_public_key:
                raw_key = self.settings.get_supabase_jwt_public_key_value()
            elif self._jwks_client:
                try:
                    signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                    raw_key = signing_key.key
                except (PyJWKClientConnectionError, urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                    logger.error("Failed to connect to JWKS endpoint: %s", exc)
                    raise AuthenticationError(
                        "AUTH_PROVIDER_UNAVAILABLE",
                        "Authentication service is temporarily unavailable. Please retry shortly.",
                        status_code=503,
                    ) from exc
                except Exception as exc:
                    logger.warning("Failed to obtain JWKS signing key: %s", type(exc).__name__)
                    raise AuthenticationError(
                        "INVALID_SIGNATURE",
                        "Unable to retrieve signing key for token.",
                        status_code=401,
                    ) from exc
            else:
                logger.error("ES token received but neither public key nor JWKS is configured.")
                raise AuthenticationError(
                    "AUTH_NOT_CONFIGURED",
                    "Asymmetric verification credentials are not configured on the server.",
                    status_code=401,
                )
            key = self._ensure_ec_public_key(raw_key)
        else:
            raise AuthenticationError(
                "INVALID_ALGORITHM",
                f"Unsupported algorithm family: {normalized_alg}",
                status_code=401,
            )

        # 3. Cryptographically decode and verify claims
        require_claims = ["exp", "sub"]
        decode_kwargs: dict[str, Any] = {
            "algorithms": [normalized_alg],
        }
        if self.settings.supabase_jwt_audience:
            decode_kwargs["audience"] = self.settings.supabase_jwt_audience
            require_claims.append("aud")
        if self.settings.resolved_jwt_issuer:
            decode_kwargs["issuer"] = self.settings.resolved_jwt_issuer
            require_claims.append("iss")
        decode_kwargs["options"] = {"require": require_claims}

        try:
            payload = jwt.decode(token, key=key, **decode_kwargs)
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationError("INVALID_TOKEN", f"Token is missing required claim: {exc}", status_code=401) from exc
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("TOKEN_EXPIRED", "Token has expired.", status_code=401) from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("INVALID_AUDIENCE", "Token audience is invalid.", status_code=401) from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError("INVALID_ISSUER", "Token issuer is invalid.", status_code=401) from exc
        except jwt.InvalidSignatureError as exc:
            raise AuthenticationError("INVALID_SIGNATURE", "Token signature is invalid.", status_code=401) from exc
        except jwt.InvalidAlgorithmError as exc:
            raise AuthenticationError("INVALID_ALGORITHM", "Token algorithm is invalid.", status_code=401) from exc
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            logger.warning("JWT verification failed with %s: %s", type(exc).__name__, exc)
            raise AuthenticationError("INVALID_TOKEN", "Token is malformed or invalid.", status_code=401) from exc

        # 4. Validate subject claim (user ID)
        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("INVALID_TOKEN", "Token is missing required 'sub' claim.")

        try:
            user_uuid = UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise AuthenticationError(
                "INVALID_TOKEN", "Token subject claim is not a valid UUID."
            ) from exc

        email = payload.get("email")
        role = payload.get("role", "authenticated")

        return AuthenticatedUser(
            user_id=user_uuid,
            email=str(email) if email else None,
            role=str(role),
            claims=payload,
        )


# ==============================================================================
# 4. FastAPI Authentication Dependencies
# ==============================================================================


def get_token_verifier(
    settings: Settings = Depends(get_settings),
) -> SupabaseTokenVerifier:
    """Dependency resolving the SupabaseTokenVerifier instance."""
    return SupabaseTokenVerifier(settings=settings)


def extract_bearer_token(request: Request) -> str | None:
    """Extract token string from 'Authorization: Bearer <token>' header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    stripped = auth_header.strip()
    if not stripped:
        return None

    if not stripped.lower().startswith("bearer"):
        raise AuthenticationError(
            "INVALID_TOKEN",
            "Authorization header must use Bearer scheme.",
        )

    parts = stripped.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        raise AuthenticationError("INVALID_TOKEN", "Bearer token cannot be empty.")

    return parts[1].strip()


async def get_current_user(
    request: Request,
    verifier: SupabaseTokenVerifier = Depends(get_token_verifier),
) -> AuthenticatedUser:
    """FastAPI dependency requiring a valid authenticated Supabase user.

    Raises:
        AuthenticationError: If token is missing, expired, or invalid.
    """
    token = extract_bearer_token(request)
    if not token:
        raise AuthenticationError(
            "AUTHENTICATION_REQUIRED", "Authentication token is required."
        )

    return verifier.verify_token(token)


# ==============================================================================
# 5. Cryptographic Server-Issued Guest Sessions
# ==============================================================================

GUEST_TOKEN_PREFIX = "gst."


def create_guest_session_token(
    session_id: UUID | None = None,
    ttl_seconds: int = 86400,
    secret: bytes | str | None = None,
) -> tuple[str, UUID, datetime]:
    """Issue a cryptographically signed, tamper-evident guest session token.

    Format: gst.<base64url_payload>.<base64url_hmac_sha256>

    Args:
        session_id: Optional UUID. If omitted, a fresh random UUID4 is generated.
        ttl_seconds: Expiration lifetime in seconds (default 86400 = 24h).
        secret: Signing key bytes or string. If omitted, derived from global settings.

    Returns:
        tuple of (token_string, session_uuid, expiration_datetime_utc)
    """
    if session_id is None:
        session_id = uuid4()

    if secret is None:
        secret = get_settings().get_guest_session_secret_bytes()
    elif isinstance(secret, str):
        secret = secret.encode("utf-8")

    if not secret or len(secret) < 32:
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest signing secret is invalid or insufficiently configured.",
        )

    now_ts = int(time.time())
    exp_ts = now_ts + ttl_seconds
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

    payload_dict = {
        "sid": str(session_id),
        "iat": now_ts,
        "exp": exp_ts,
    }
    payload_json = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    payload_b64 = urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")

    signature = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    token = f"{GUEST_TOKEN_PREFIX}{payload_b64}.{sig_b64}"
    return token, session_id, expires_at


def verify_guest_session_token(
    token: str,
    secret: bytes | str | None = None,
) -> UUID:
    """Validate and decode a server-issued guest session token.

    Verifies format, HMAC-SHA256 signature, expiration, and UUID structure.
    Strictly rejects raw UUIDs, forged signatures, and expired tokens.

    Args:
        token: The signed guest session token.
        secret: Signing key bytes or string. If omitted, derived from global settings.

    Returns:
        The verified guest session UUID.

    Raises:
        AuthenticationError: If token is malformed, forged, tampered, raw UUID, or expired.
    """
    if not token or not isinstance(token, str):
        raise AuthenticationError("INVALID_GUEST_SESSION", "Guest session token is missing or empty.")

    token = token.strip()
    if not token.startswith(GUEST_TOKEN_PREFIX):
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token format is invalid, raw, or forged.",
        )

    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "gst":
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token structure is invalid.",
        )

    payload_b64 = parts[1]
    sig_b64 = parts[2]

    if secret is None:
        secret = get_settings().get_guest_session_secret_bytes()
    elif isinstance(secret, str):
        secret = secret.encode("utf-8")

    if not secret or len(secret) < 32:
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest signing secret is invalid or insufficiently configured.",
        )

    expected_sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    expected_sig_b64 = urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        logger.warning("Rejected guest session token with invalid HMAC signature.")
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token signature is invalid or forged.",
        )

    try:
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = urlsafe_b64decode(padded_b64.encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to decode guest session token payload: %s", type(exc).__name__)
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token payload is malformed.",
        ) from exc

    exp_ts = payload.get("exp")
    if not isinstance(exp_ts, (int, float)) or time.time() > exp_ts:
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token has expired.",
        )

    sid_str = payload.get("sid")
    if not sid_str:
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session token is missing session identifier.",
        )

    try:
        session_uuid = UUID(str(sid_str))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError(
            "INVALID_GUEST_SESSION",
            "Guest session identifier is not a valid UUID.",
        ) from exc

    return session_uuid


async def get_current_user_or_guest(
    request: Request,
    verifier: SupabaseTokenVerifier = Depends(get_token_verifier),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser | GuestUser:
    """FastAPI dependency providing authenticated identity or isolated guest session.

    Policy:
    - If Authorization header is present: token is verified strictly. Invalid tokens fail with 401.
    - If Authorization header is absent:
      - If STORAGE_BACKEND is 'postgres': guest access is strictly rejected with 401.
      - If APP_ENV is 'production' and ALLOW_GUEST_MODE is False: rejected with 401.
      - Otherwise: guest access is permitted in-memory.
        - If X-Guest-Session-ID header is present: verified cryptographically.
          Invalid, forged, raw, or expired tokens fail with 401.
        - If planproof_guest_session cookie is present: verified cryptographically.
          Invalid, forged, raw, or expired tokens fail with 401.
        - If neither is present: a new isolated server-issued session is created for this request,
          preventing any persistent shared guest identity.
    """
    token = extract_bearer_token(request)
    if token:
        return verifier.verify_token(token)

    # Enforce PostgreSQL persistence policy: guests cannot use PostgreSQL storage
    if settings.storage_backend == "postgres":
        logger.warning("Unauthenticated request rejected because storage backend is 'postgres'")
        raise AuthenticationError(
            "AUTHENTICATION_REQUIRED",
            "Authentication is required when PostgreSQL storage is enabled.",
        )

    # Enforce Production policy
    if settings.app_env == "production" and not settings.allow_guest_mode:
        logger.warning("Unauthenticated guest access is disabled in production")
        raise AuthenticationError(
            "AUTHENTICATION_REQUIRED",
            "Guest access is disabled in production. Please sign in.",
        )

    secret = settings.get_guest_session_secret_bytes()
    guest_header = request.headers.get("X-Guest-Session-ID")
    if guest_header and guest_header.strip():
        # Strictly verify client-supplied guest session header
        verified_guest_id = verify_guest_session_token(guest_header.strip(), secret=secret)
        return GuestUser(user_id=verified_guest_id)

    # Check cookie fallback
    guest_cookie = request.cookies.get("planproof_guest_session")
    if guest_cookie and guest_cookie.strip():
        # Strictly verify client-supplied guest session cookie
        verified_guest_id = verify_guest_session_token(guest_cookie.strip(), secret=secret)
        return GuestUser(user_id=verified_guest_id)

    # No token provided: generate a fresh isolated server-issued session
    # This prevents unauthenticated callers from ever sharing a persistent 'None' identity
    new_token, new_guest_id, expires_at = create_guest_session_token(
        ttl_seconds=settings.guest_session_ttl_seconds,
        secret=secret,
    )
    request.state.new_guest_token = new_token
    request.state.new_guest_expires_at = expires_at
    return GuestUser(user_id=new_guest_id)

