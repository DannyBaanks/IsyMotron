# Identity seam V0

`core/isymotron/identity.py` is a mock OIDC-shaped adapter. It proves the
shape of authorization-code login, state binding between callback and code,
issuer/audience/nonce validation, expiry, one-time codes, and signed ID-token
verification.

Identity produces a `subject` for receipts and lease requests. It does **not**
produce capabilities, scopes, leases, or grants; those remain local host
decisions.

State mismatch is rejected before the code is consumed, so a valid callback
can still be retried with the correct browser transaction.

```text
py -m pytest tests/test_identity.py -q
4 passed
```

This is not a production identity provider and does not contact a network.
