"""Identity seam V0: authentication shapes identity, never authority."""

from urllib.parse import parse_qs, urlparse

import pytest

from isymotron.identity import MockIdentityProvider


def test_oidc_shaped_code_flow_returns_verified_subject():
    provider = MockIdentityProvider()
    request = provider.begin("console", "https://client.invalid/callback")
    query = parse_qs(urlparse(request.url).query)
    callback = provider.authorize(
        client_id="console", redirect_uri=request.redirect_uri,
        subject="user:danny", state=query["state"][0], nonce=query["nonce"][0],
    )
    callback_query = parse_qs(urlparse(callback).query)
    session = provider.exchange(
        callback_query["code"][0], client_id="console",
        redirect_uri=request.redirect_uri, state=callback_query["state"][0], now=100,
    )
    claims = provider.verify(session.id_token, client_id="console", nonce=request.nonce, now=100)
    assert claims.subject == "user:danny"
    assert claims.issuer == "https://mock.identity.invalid"


def test_authorization_code_is_one_time_and_token_tampering_fails():
    provider = MockIdentityProvider()
    request = provider.begin("console", "https://client.invalid/callback")
    callback = provider.authorize(
        client_id="console", redirect_uri=request.redirect_uri,
        subject="user:danny", state=request.state, nonce=request.nonce,
    )
    code = parse_qs(urlparse(callback).query)["code"][0]
    session = provider.exchange(code, client_id="console", redirect_uri=request.redirect_uri, state=request.state, now=100)
    with pytest.raises(ValueError, match="already-used"):
        provider.exchange(code, client_id="console", redirect_uri=request.redirect_uri, state=request.state, now=100)
    parts = session.id_token.split(".")
    parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    with pytest.raises(ValueError, match="signature"):
        provider.verify(".".join(parts), client_id="console", nonce=request.nonce, now=100)


def test_identity_does_not_contain_or_issue_capabilities():
    provider = MockIdentityProvider()
    request = provider.begin("console", "https://client.invalid/callback")
    callback = provider.authorize(
        client_id="console", redirect_uri=request.redirect_uri,
        subject="user:limited", state=request.state, nonce=request.nonce,
    )
    code = parse_qs(urlparse(callback).query)["code"][0]
    session = provider.exchange(code, client_id="console", redirect_uri=request.redirect_uri, state=request.state, now=100)
    assert set(session.claims.to_dict()) == {"iss", "sub", "aud", "iat", "exp", "nonce"}
    assert "capabilities" not in session.claims.to_dict()


def test_state_from_another_login_is_rejected_without_consuming_code():
    provider = MockIdentityProvider()
    first = provider.begin("console", "https://client.invalid/callback")
    second = provider.begin("console", "https://client.invalid/callback")
    callback = provider.authorize(
        client_id="console", redirect_uri=first.redirect_uri,
        subject="user:danny", state=first.state, nonce=first.nonce,
    )
    code = parse_qs(urlparse(callback).query)["code"][0]
    with pytest.raises(ValueError, match="state mismatch"):
        provider.exchange(code, client_id="console", redirect_uri=second.redirect_uri,
                          state=second.state, now=100)
    session = provider.exchange(code, client_id="console", redirect_uri=first.redirect_uri,
                                state=first.state, now=100)
    assert session.claims.subject == "user:danny"
