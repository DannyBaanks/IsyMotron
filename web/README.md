# ISyMotron surface

The `web/` folder is a Next.js App Router surface only. Python remains the
authority plane; this UI never decides or grants capability.

**Privacy limitation:** `/api/dashboard` does not authenticate its visitor.
If a backend token is configured, anyone who can reach this Next.js server can
request the backend state through the proxy. Keep the server on localhost and
do not expose it to a network or the internet with real data until visitor
authentication and a restricted response have been implemented and verified.

## Local run

```bash
cd web
npm install
ISYMOTRON_SESSION_TOKEN="<local console token>" npm run dev
```

The default backend is `http://127.0.0.1:8760`. Override it with
`ISYMOTRON_BACKEND_URL`. Without a session token or reachable backend, the
surface intentionally renders its demo state and labels itself `DEMO SURFACE`.

## Checks

```bash
npm test
npm run build
```
