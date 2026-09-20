"""Mock OIDC-shaped identity seam.

This adapter proves the protocol shape only. Identity claims produce a stable
subject for receipts and lease requests; they never grant capabilities. A
real provider can replace this module without changing the host contract.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode


CONTRACT = "identity-seam/v0"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class IdentityClaims:
    issuer: str
    subject: str
    audience: str
    issued_at: int
    expires_at: int
    nonce: str

    def to_dict(self) -> dict[str, object]:
        return {
            "iss": self.issuer,
            "sub": self.subject,
            "aud": self.audience,
            "iat": self.issued_at,
            "exp": self.expires_at,
            "nonce": self.nonce,
        }


@dataclass(frozen=True)
class LoginRequest:
    state: str
    nonce: str
    redirect_uri: str
    url: str


@dataclass(frozen=True)
class IdentitySession:
    claims: IdentityClaims
    id_token: str


class MockIdentityProvider:
    """In-memory authorization-code provider with JWT-shaped signed tokens."""

    def __init__(self, issuer: str = "https://mock.identity.invalid", *, secret: bytes = b"isyco-test-secret"):
        self.issuer = issuer.rstrip("/")
        self._secret = secret
        self._codes: dict[str, tuple[str, str, str, str, str]] = {}

    def begin(self, client_id: str, redirect_uri: str) -> LoginRequest:
        state = secrets.token_urlsafe(18)
        nonce = secrets.token_urlsafe(18)
        query = urlencode({
            "response_type": "code", "client_id": client_id,
            "redirect_uri": redirect_uri, "scope": "openid",
            "state": state, "nonce": nonce,
        })
        return LoginRequest(state, nonce, redirect_uri, f"{self.issuer}/authorize?{query}")

    def authorize(self, *, client_id: str, redirect_uri: str, subject: str, state: str, nonce: str) -> str:
        code = secrets.token_urlsafe(24)
        self._codes[code] = (client_id, redirect_uri, subject, nonce, state)
        return f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"

    def exchange(self, code: str, *, client_id: str, redirect_uri: str,
                 state: str, now: int | None = None) -> IdentitySession:
        record = self._codes.get(code)
        if record is None:
            raise ValueError("invalid or already-used authorization code")
        expected_client, expected_redirect, subject, nonce, expected_state = record
        if (client_id, redirect_uri) != (expected_client, expected_redirect):
            raise ValueError("authorization code client or redirect mismatch")
        if state != expected_state:
            raise ValueError("authorization code state mismatch")
        self._codes.pop(code)
        issued = int(time.time() if now is None else now)
        claims = IdentityClaims(self.issuer, subject, client_id, issued, issued + 300, nonce)
        return IdentitySession(claims, self._sign(claims.to_dict()))

    def verify(self, token: str, *, client_id: str, nonce: str, now: int | None = None) -> IdentityClaims:
        try:
            header, payload, signature = token.split(".")
            if json.loads(_unb64(header).decode("utf-8")) != {"alg": "HS256", "typ": "JWT"}:
                raise ValueError("unexpected token header")
            signed = f"{header}.{payload}".encode("ascii")
            expected = _b64(hmac.new(self._secret, signed, hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid token signature")
            data = json.loads(_unb64(payload).decode("utf-8"))
            claims = IdentityClaims(
                issuer=data["iss"], subject=data["sub"], audience=data["aud"],
                issued_at=int(data["iat"]), expires_at=int(data["exp"]), nonce=data["nonce"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"invalid identity token: {exc}") from exc
        current = int(time.time() if now is None else now)
        if claims.issuer != self.issuer or claims.audience != client_id:
            raise ValueError("issuer or audience mismatch")
        if claims.nonce != nonce:
            raise ValueError("nonce mismatch")
        if current < claims.issued_at or current >= claims.expires_at:
            raise ValueError("identity token expired or not yet valid")
        return claims

    def _sign(self, claims: dict[str, object]) -> str:
        header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
        signed = f"{header}.{payload}".encode("ascii")
        return f"{header}.{payload}.{_b64(hmac.new(self._secret, signed, hashlib.sha256).digest())}"
