# ISyMotron surface

The `web/` folder is a Next.js App Router surface only. Python remains the
authority plane; this UI never decides or grants capability.

**Access control:** `/api/dashboard` requires `Authorization: Bearer <key>`,
where the key is `ISYMOTRON_DASHBOARD_TOKEN` (separate from the backend
`ISYMOTRON_SESSION_TOKEN`, which never leaves the server). If a session token
is set but no dashboard key is configured, the route fails closed (503). The
browser keeps the key only in `sessionStorage`. Keys are compared in constant
time. Still keep this server on localhost unless you add TLS in front of it.

## Local run

```bash
cd web
npm install
ISYMOTRON_SESSION_TOKEN="<local console token>" ISYMOTRON_DASHBOARD_TOKEN="<visitor key>" npm run dev
```

The default backend is `http://127.0.0.1:8760`. Override it with
`ISYMOTRON_BACKEND_URL`. Without a session token or reachable backend, the
surface intentionally renders its demo state and labels itself `DEMO SURFACE`.

## Checks

```bash
npm test
npm run build
```
