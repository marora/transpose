from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from aiohttp import web

from transpose.config.settings import Settings

_ADMIN_PREFIX = "/admin/"


class EntraAuthError(Exception):
    """Raised when an Entra access token cannot be validated."""


@dataclass(slots=True)
class CachedJwks:
    """Cached JWKS document plus the monotonic timestamp it was fetched."""

    fetched_at: float
    keys_by_kid: dict[str, dict[str, Any]]


class EntraTokenValidator:
    """Validate Entra bearer tokens for admin routes with cached JWKS lookup."""

    def __init__(self, settings: Settings):
        self._tenant_id = settings.entra_tenant_id
        self._expected_issuer = settings.get_entra_issuer()
        self._expected_audience = settings.entra_admin_audience
        self._expected_scope = self._extract_scope_name(self._expected_audience)
        self._discovery_url = settings.get_entra_discovery_url()
        self._cache_ttl_seconds = settings.entra_jwks_cache_ttl_seconds
        self._lock = asyncio.Lock()
        self._jwks_cache: CachedJwks | None = None

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate the JWT signature and required claims."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise EntraAuthError("Malformed bearer token.") from exc

        if header.get("alg") != "RS256":
            raise EntraAuthError("Unsupported token signing algorithm.")

        kid = header.get("kid")
        if not kid:
            raise EntraAuthError("Missing token key identifier.")

        signing_key = await self._get_signing_key(kid)
        try:
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=["RS256"],
                options={"require": ["exp", "iss"]},
                issuer=self._expected_issuer,
                audience=self._allowed_audiences,
            )
        except jwt.ExpiredSignatureError as exc:
            raise EntraAuthError("Bearer token has expired.") from exc
        except jwt.ImmatureSignatureError as exc:
            raise EntraAuthError("Bearer token is not active yet.") from exc
        except jwt.InvalidIssuerError as exc:
            raise EntraAuthError("Bearer token issuer is invalid.") from exc
        except jwt.InvalidAudienceError as exc:
            raise EntraAuthError("Bearer token audience is invalid.") from exc
        except jwt.PyJWTError as exc:
            raise EntraAuthError("Bearer token validation failed.") from exc

        self._validate_scope(claims)
        return claims

    @property
    def _allowed_audiences(self) -> tuple[str, ...]:
        audiences = {self._expected_audience}
        resource_audience = self._resource_audience
        if resource_audience:
            audiences.add(resource_audience)
        return tuple(audiences)

    @property
    def _resource_audience(self) -> str | None:
        if self._expected_audience.startswith("api://") and "/" in self._expected_audience[6:]:
            return self._expected_audience.rsplit("/", 1)[0]
        return None

    async def _get_signing_key(self, kid: str) -> Any:
        keys_by_kid = await self._get_jwks_keys()
        jwk = keys_by_kid.get(kid)
        if jwk is None:
            keys_by_kid = await self._get_jwks_keys(force_refresh=True)
            jwk = keys_by_kid.get(kid)
        if jwk is None:
            raise EntraAuthError("Signing key not found for bearer token.")
        return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

    async def _get_jwks_keys(self, *, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        cache = self._jwks_cache
        now = time.monotonic()
        if not force_refresh and cache and now - cache.fetched_at < self._cache_ttl_seconds:
            return cache.keys_by_kid

        async with self._lock:
            cache = self._jwks_cache
            now = time.monotonic()
            if not force_refresh and cache and now - cache.fetched_at < self._cache_ttl_seconds:
                return cache.keys_by_kid

            discovery = await self._fetch_json(self._discovery_url)
            jwks_uri = discovery.get("jwks_uri")
            if not jwks_uri:
                raise EntraAuthError("OpenID discovery document did not include a JWKS URI.")

            jwks = await self._fetch_json(jwks_uri)
            keys = jwks.get("keys") or []
            keys_by_kid = {key["kid"]: key for key in keys if key.get("kid")}
            if not keys_by_kid:
                raise EntraAuthError("JWKS document did not include any signing keys.")

            self._jwks_cache = CachedJwks(fetched_at=now, keys_by_kid=keys_by_kid)
            return keys_by_kid

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EntraAuthError("Unable to fetch Entra signing metadata.") from exc
        return response.json()

    def _validate_scope(self, claims: dict[str, Any]) -> None:
        if not self._expected_scope:
            return

        audiences = claims.get("aud")
        if isinstance(audiences, str):
            audience_values = {audiences}
        elif isinstance(audiences, list):
            audience_values = {str(value) for value in audiences}
        else:
            audience_values = set()

        if self._expected_audience in audience_values:
            return

        resource_audience = self._resource_audience
        if resource_audience and resource_audience in audience_values:
            scopes = set(str(claims.get("scp", "")).split())
            if self._expected_scope not in scopes:
                raise EntraAuthError("Bearer token is missing the required dashboard scope.")

    @staticmethod
    def _extract_scope_name(audience: str) -> str | None:
        if audience.startswith("api://") and "/" in audience[6:]:
            return audience.rsplit("/", 1)[1]
        return None


def is_admin_path(path: str) -> bool:
    """Return True when the request path should be protected by Entra auth."""
    return path == "/admin" or path.startswith(_ADMIN_PREFIX)


@web.middleware
async def entra_admin_middleware(request: web.Request, handler):
    """Require a valid Entra bearer token on all /admin/* routes."""
    if not is_admin_path(request.path):
        return await handler(request)

    token = _extract_bearer_token(request)
    if not token:
        return _unauthorized_response(request, "Bearer token required.")

    validator: EntraTokenValidator | None = request.app.get("entra_token_validator")
    if validator is None:
        return _unauthorized_response(request, "Admin auth is not configured.", status=503)

    try:
        claims = await validator.validate(token)
    except EntraAuthError as exc:
        return _unauthorized_response(request, str(exc))

    request["user"] = {
        "name": claims.get("name") or claims.get("preferred_username"),
        "oid": claims.get("oid"),
        "scp": claims.get("scp", ""),
        "claims": claims,
    }
    return await handler(request)


def _extract_bearer_token(request: web.Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    return auth_header[7:].strip() or None


def _unauthorized_response(request: web.Request, detail: str, *, status: int = 401) -> web.Response:
    challenge = (
        "Bearer "
        f'authorization_uri="{request.app.get("entra_authority", "")}", '
        f'error="invalid_token", error_description="{detail}"'
    )
    error_body = {
        "error": {
            "code": "UNAUTHORIZED",
            "message": detail,
            "request_id": request.get("request_id", "unknown"),
        }
    }
    return web.json_response(
        error_body,
        status=status,
        headers={"WWW-Authenticate": challenge},
    )
