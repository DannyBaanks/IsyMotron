# Identity seam V0

`core/isymotron/identity.py` is a mock OIDC-shaped adapter. It proves the
shape of authorization-code login, issuer/audience/nonce validation, expiry,
one-time codes, and signed ID-token verification.

Identity produces a `subject` for receipts and lease requests. It does **not**
produce capabilities, scopes, leases, or grants; those remain local host
decisions.

```text
py -m pytest tests/test_identity.py -q
3 passed
```

This is not a production identity provider and does not contact a network.
