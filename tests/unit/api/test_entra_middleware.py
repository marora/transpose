from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from transpose.api import create_app

TENANT_ID = "48af2a40-dd60-4e0d-ba42-f0fac9a31d93"
CLIENT_ID = "5ffe7826-3caa-41a8-9359-a5dd3aee4407"
AUDIENCE = "api://transpose-admin/Dashboard.Read"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
DISCOVERY_URL = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0/.well-known/openid-configuration"
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"


def _build_valid_token() -> tuple[str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = "test-kid"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "aud": "api://transpose-admin",
            "iss": ISSUER,
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=30),
            "iat": now - timedelta(seconds=30),
            "name": "Transpose Admin",
            "oid": "00000000-0000-0000-0000-000000000123",
            "scp": "Dashboard.Read",
            "tid": TENANT_ID,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    return token, jwk


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_AUDIENCE", AUDIENCE)


async def _make_client(aiohttp_client, fetch_json: AsyncMock | None = None):
    if fetch_json is None:
        fetch_json = AsyncMock(side_effect=AssertionError("JWKS fetch should not be called"))

    with patch("transpose.observability.tracing.configure_tracing"):
        app = create_app()
    if "entra_token_validator" in app:
        app["entra_token_validator"]._fetch_json = fetch_json
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_non_admin_routes_remain_unaffected(admin_env, aiohttp_client) -> None:
    client = await _make_client(aiohttp_client)

    health_response = await client.get("/health")
    assert health_response.status == 200

    translate_response = await client.post(
        "/translate",
        json={
            "blob_uri": "https://storage.blob.core.windows.net/source/book.pdf",
            "title": "Smoke Test Book",
            "language": "hindi",
        },
    )
    assert translate_response.status == 200


@pytest.mark.asyncio
async def test_admin_route_requires_bearer_token(admin_env, aiohttp_client) -> None:
    client = await _make_client(aiohttp_client)

    response = await client.get("/admin/api/test")

    assert response.status == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_admin_route_rejects_malformed_token(admin_env, aiohttp_client) -> None:
    client = await _make_client(aiohttp_client)

    response = await client.get("/admin/api/test", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status == 401
    body = await response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_admin_route_accepts_valid_token(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    fetch_json = AsyncMock(
        side_effect=[
            {"issuer": ISSUER, "jwks_uri": JWKS_URI},
            {"keys": [jwk]},
        ]
    )
    client = await _make_client(aiohttp_client, fetch_json=fetch_json)

    response = await client.get("/admin/api/test", headers={"Authorization": f"Bearer {token}"})

    assert response.status == 200
    body = await response.json()
    assert body["status"] == "ok"
    assert body["user"]["name"] == "Transpose Admin"
    assert body["user"]["oid"] == "00000000-0000-0000-0000-000000000123"
    assert body["user"]["scp"] == "Dashboard.Read"
    assert fetch_json.await_args_list[0].args == (DISCOVERY_URL,)
    assert fetch_json.await_args_list[1].args == (JWKS_URI,)
