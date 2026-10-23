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

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, Request
from jwt import PyJWKClient

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Domain Exceptions
# ==============================================================================


class AuthenticationError(Exception):
    """Raised when request authentication fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
        return f"GuestUser(user_id={self.user_id})"


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

        # 2. Resolve verification key based on algorithm
        key: Any = None
        if normalized_alg.startswith("HS"):
            jwt_secret = self.settings.get_supabase_jwt_secret_value()
            if not jwt_secret:
                logger.error("HS token received but SUPABASE_JWT_SECRET is not configured.")
                raise AuthenticationError(
                    "AUTH_NOT_CONFIGURED",
                    "Authentication verification credentials are not configured on the server.",
                )
            key = jwt_secret
        elif normalized_alg.startswith("RS") or normalized_alg.startswith("ES"):
            public_key = self.settings.get_supabase_jwt_public_key_value()
            if public_key:
                key = public_key
            elif self._jwks_client:
                try:
                    signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                    key = signing_key.key
                except Exception as exc:
                    logger.warning("Failed to obtain JWKS signing key: %s", type(exc).__name__)
                    raise AuthenticationError(
                        "INVALID_SIGNATURE", "Unable to retrieve signing key for token."
                    ) from exc
            else:
                logger.error("Asymmetric token received but neither public key nor JWKS is configured.")
                raise AuthenticationError(
                    "AUTH_NOT_CONFIGURED",
                    "Asymmetric verification credentials are not configured on the server.",
                )
        else:
            raise AuthenticationError("INVALID_ALGORITHM", f"Unsupported algorithm family: {normalized_alg}")

        # 3. Cryptographically decode and verify claims
        decode_kwargs: dict[str, Any] = {
            "algorithms": [normalized_alg],
            "options": {"require": ["exp", "sub"]},
        }
        if self.settings.supabase_jwt_audience:
            decode_kwargs["audience"] = self.settings.supabase_jwt_audience
        if self.settings.resolved_jwt_issuer:
            decode_kwargs["issuer"] = self.settings.resolved_jwt_issuer

        try:
            payload = jwt.decode(token, key=key, **decode_kwargs)
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationError("INVALID_TOKEN", f"Token is missing required claim: {exc}") from exc
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("TOKEN_EXPIRED", "Token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("INVALID_AUDIENCE", "Token audience is invalid.") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError("INVALID_ISSUER", "Token issuer is invalid.") from exc
        except jwt.InvalidSignatureError as exc:
            raise AuthenticationError("INVALID_SIGNATURE", "Token signature is invalid.") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise AuthenticationError("INVALID_ALGORITHM", "Token algorithm is invalid.") from exc
        except (jwt.DecodeError, jwt.InvalidTokenError) as exc:
            raise AuthenticationError("INVALID_TOKEN", "Token is malformed or invalid.") from exc

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
      - Otherwise: guest access is permitted in-memory. Guest events are isolated.
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

    # Ephemeral guest user
    guest_header = request.headers.get("X-Guest-Session-ID")
    guest_id: UUID | None = None
    if guest_header and isinstance(guest_header, str):
        try:
            guest_id = UUID(guest_header.strip())
        except (ValueError, TypeError):
            guest_id = None

    return GuestUser(user_id=guest_id)
