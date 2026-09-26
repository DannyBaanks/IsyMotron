# Model providers

The planner talks to one seam, `agents/provider.py`: the OpenAI-compatible
`/v1/chat/completions` protocol over `urllib`, no SDK. A provider is a preset —
a base URL, where its key comes from, a default model — not code.

| `ISYMOTRON_PROVIDER` | Where | Key | Default model | JSON mode |
|---|---|---|---|---|
| `nvidia` (default) | `integrate.api.nvidia.com/v1` | `NVIDIA_NIM_API_KEY` (required) | `nvidia/nemotron-3-super-120b-a12b` | no (prompt only) |
| `nebius` | Nebius Token Factory | `NEBIUS_API_KEY` (required) | same | no (prompt only) |
| `ollama` | `127.0.0.1:11434/v1`, or `$OLLAMA_HOST` | none (`OLLAMA_API_KEY` if your server wants one) | `llama3.1:8b` | yes |
| `llamacpp` | `127.0.0.1:8080/v1` (`llama-server`) | none (`LLAMACPP_API_KEY` for `--api-key`) | whatever the server loaded | yes |

Overrides for any preset: `ISYMOTRON_MODEL`, `ISYMOTRON_BASE_URL`. LM Studio,
vLLM and other OpenAI-compatible local servers work through `llamacpp` plus
`ISYMOTRON_BASE_URL`.

## Llama

Llama is a model family, not a server. Two ways in:

- **Local:** `ollama pull llama3.1:8b` (or `llama3.2:1b` on small machines) and
  `ISYMOTRON_PROVIDER=ollama`; or a GGUF under `llama-server` and
  `ISYMOTRON_PROVIDER=llamacpp`.
- **Hosted:** NVIDIA NIM and Nebius also serve Llama models; set
  `ISYMOTRON_MODEL` to their id on that provider. INFERRED, not yet run here.

## What does not change

Which model proposes a plan never changes what a host allows. The planner
refuses invented capabilities and undeclared parameters; the host refuses
anything outside a granted scope; every decision ends in a sealed receipt. A
smaller model produces more refusals, never more reach. The catalogue a model
sees carries logical names only (`hostfs://photos`), so a hosted provider never
learns your folder layout — and with a local one, the prompt never leaves the
machine at all.

## Safety rails in the seam

- A key is never sent over plain `http://` to anything but this machine; the
  provider refuses to start instead (https, or a loopback server).
- No key, no `Authorization` header: an empty bearer token is not "no auth".
- A local server that refuses the connection is not retried: it is not
  running, and the error says how to start it instead of spinning through a
  90 s backoff. Hosted providers keep their retries (networks come back).
- JSON mode (`response_format: json_object`) is sent only to presets that
  declare it; hosted presets are byte-for-byte unchanged.

## Evidence

| Claim | Status | Where |
|---|---|---|
| Presets, keyless config, header/plain-http rails, JSON mode, fail-fast | **DEMONSTRATED** (stub server speaking the Ollama/OpenAI surface; 6 mutants, 6 caught) | `tests/test_local_provider.py` |
| A real Llama on Ollama: round trip, and authority holds for whatever it plans | measured per run | `.github/workflows/local-model.yml` → `local-model-report.json` |
| Plan quality of small local models | measured, not promised | the same report |
| Llama via NVIDIA NIM / Nebius | NOT_DEMONSTRATED | set `ISYMOTRON_MODEL` and run `isymotron nemotron` |
