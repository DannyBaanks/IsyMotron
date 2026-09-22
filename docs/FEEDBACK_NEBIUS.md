# Feedback — Nebius Token Factory / NVIDIA Nemotron

Submitted as part of the Nebius × NVIDIA Global AI Hackathon (track: Best Apps and Agents).

## Nebius Token Factory

**What worked well:**
- OpenAI-compatible `/v1/chat/completions` endpoint — zero SDK lock-in, `urllib` only.
- Model `nvidia/nemotron-3-super-120b-a12b` served identically on Nebius and NVIDIA NIM.
- Latency measured at ~0.65 s round-trip (cold) on `tools/nemotron_check.py` probe.
- `reasoning_content` field exposed cleanly — chain-of-thought available for debugging.
- Token Factory credits model is transparent; no surprise billing.

**Pain points / suggestions:**
1. **Model listing vs. servability**: `/models` lists `nemotron-nano-3-30b-a3b` but it returns 404 on invocation. Listed ≠ servable — please align or document.
2. **Cold-start 503s**: Measured 1 HTTP 503 in 12 back-to-back calls to NVIDIA NIM; Nebius showed 0 in our probe, but a larger sample would help. Consider a warm-pool or published SLO.
3. **Rate-limit headers**: Response lacks `Retry-After` / `X-RateLimit-*` headers. Clients must infer from 429 body.
4. **Regional endpoints**: Only `us-central1` documented; EU/LATAM builders would benefit from regional proximity.
5. **Streaming**: Works, but `reasoning_content` only arrives in final chunk for non-streaming; streaming reasoning would be valuable for UX.

## NVIDIA Nemotron (3 Ultra / Super / Nano)

**What worked well:**
- Strong instruction following for structured JSON plans (our planner schema).
- Reasoning traces (`reasoning_content`) are detailed and useful for audit.
- Refuses hallucinated capabilities cleanly when schema + catalogue are tight.

**Pain points / suggestions:**
1. **Token budget sensitivity**: At `max_tokens=16` the model returns raw CoT in `content` instead of the answer; at 48 it returns clean JSON. This is a sharp cliff — documentation should warn "always budget ≥200 tokens for Nemotron-3-Super structured output".
2. **Finish reason `length` vs `stop`**: When budget is tight, `finish_reason="length"` and the response is CoT, not a truncated answer. Clients must check this before parsing.
3. **No official Python client**: Using `urllib` is fine but an official lightweight client with retry/backoff would reduce boilerplate.

## Integration with IsyMotron

IsyMotron's provider seam (`agents/provider.py`) treats Nebius and NVIDIA NIM as configuration-only (same protocol, different `base_url` and key). Switching is one env var: `ISYMOTRON_PROVIDER=nebius` + `NEBIUS_API_KEY`.

The planner (`agents/planner.py`) never sees physical paths — only logical `hostfs://` names. This means the model never learns `C:/Users/...`, and a provider swap changes *how* a plan is proposed, not *what* the host enforces.

## Reproducibility

- Probe artifact: `evidence/M3/probe_nebius.json` (sealed with `evidence/M3/hashes.json` + `evidence/M3/RUN.md`).
- CI runs on `windows-latest`; live-model tests self-skip without keys.
- All acceptance gates (`py -m pytest -q`) are offline and deterministic.

## Wishlist for next cycle

- Nebius Serverless Endpoints for deploying the IsyMotron console as a managed service.
- Tavily integration for web-grounded planning (bonus track).
- Pre-suspend notification on Windows (currently `NOT_DEMONSTRATED`).