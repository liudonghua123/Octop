"""Tests for OIDC ID token verification."""

from __future__ import annotations

import json
import logging
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from octop.infra.auth.sso.id_token import verify_id_token


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_client(signing_key: rsa.RSAPrivateKey) -> httpx.Client:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://issuer.example/jwks"
        return httpx.Response(200, json={"keys": [jwk]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _jwks_client_with_keys(jwks: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://issuer.example/jwks"
        return httpx.Response(200, json=jwks)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _token(
    signing_key: rsa.RSAPrivateKey,
    *,
    issuer: str = "https://issuer.example",
    nonce: str = "nonce",
    kid: str | None = "test-key",
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "aud": ["octop-client", "other-client"],
            "exp": now + 300,
            "iat": now,
            "nonce": nonce,
            "sub": "user-1",
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": kid} if kid else {},
    )


def test_verify_id_token_accepts_issuer_with_trailing_slash(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    issuer = "https://issuer.example/application/o/app/"
    claims = verify_id_token(
        _token(signing_key, issuer=issuer),
        jwks_uri="https://issuer.example/jwks",
        issuer=issuer,
        client_id="octop-client",
        nonce="nonce",
        httpx=jwks_client,
    )
    assert claims["sub"] == "user-1"


def test_verify_id_token_rejects_trailing_slash_mismatch(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    with pytest.raises(jwt.InvalidIssuerError):
        verify_id_token(
            _token(signing_key, issuer="https://issuer.example/application/o/app/"),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example/application/o/app",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_rejects_wrong_issuer(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    with pytest.raises(jwt.InvalidIssuerError):
        verify_id_token(
            _token(signing_key, issuer="https://other-issuer.example"),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_rejects_wrong_nonce(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    with pytest.raises(jwt.InvalidTokenError, match="nonce"):
        verify_id_token(
            _token(signing_key, nonce="unexpected"),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_rejects_disallowed_algorithm(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    now = int(time.time())
    hs_token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "octop-client",
            "exp": now + 300,
            "iat": now,
            "nonce": "nonce",
            "sub": "user-1",
        },
        "symmetric-secret-at-least-32-bytes!!",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(jwt.InvalidTokenError, match="not allowed"):
        verify_id_token(
            hs_token,
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_falls_back_to_single_key_without_kid(
    signing_key: rsa.RSAPrivateKey, caplog: pytest.LogCaptureFixture
) -> None:
    """Single-key IdPs (e.g. YNU) omit ``kid`` — must verify via the only key."""
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk["use"] = "sig"  # no kid, no alg — mirrors the real YNU JWKS
    client = _jwks_client_with_keys({"keys": [jwk]})
    with caplog.at_level(logging.WARNING, logger="octop.infra.auth.sso.id_token"):
        claims = verify_id_token(
            _token(signing_key, kid=None),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=client,
        )
    assert claims["sub"] == "user-1"
    assert any("falling back" in r.message for r in caplog.records)


def test_verify_id_token_still_rejects_missing_kid_with_multiple_keys(
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """No kid + multiple JWKS keys is ambiguous — must still fail loudly."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk_a = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk_b = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(other.public_key()))
    for jwk in (jwk_a, jwk_b):
        jwk["use"] = "sig"
    client = _jwks_client_with_keys({"keys": [jwk_a, jwk_b]})
    with pytest.raises(jwt.InvalidTokenError, match="missing a key ID"):
        verify_id_token(
            _token(signing_key, kid=None),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=client,
        )


def test_verify_id_token_rejects_wrong_signature_in_kidless_fallback(
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """Fallback verifies the signature — a token from another key must fail."""
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk["use"] = "sig"
    client = _jwks_client_with_keys({"keys": [jwk]})
    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidSignatureError):
        verify_id_token(
            _token(rogue, kid=None),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=client,
        )
