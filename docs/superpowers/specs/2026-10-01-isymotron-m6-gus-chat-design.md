# M6.1 — GUS chat in IsyMotron Móvil

**Status:** design for user review

**Roadmap:** `docs/mobile/ROADMAP.md`, M6.1

**Date:** 2026-10-01

## Goal

Add a GUS chat to the native IsyMotron mobile app. On-device inference is the default and works without network access after a model is installed. A remote provider is used only after the user selects remote mode. A local runtime, model, or network failure must never silently change the selected route.

## Existing implementation and reuse

IsyMotron is a Capacitor app with an existing Home screen and native iOS and Android shells. It has no GUS chat or native inference plugin yet. The reference implementation in iSyCode Móvil stores active models in app-private storage, then provides **Guardar copia** and **Importar** using the platform file picker. Import accepts models matching its pinned catalogue and verifies their size and SHA-256. Its current source pin is `9c8a659840045cb31da7b501022645a194f4422d`.

M6.1 follows that storage lifecycle: inference uses an app-private verified model; export creates a user-managed copy outside the app; import restores and verifies that copy. It does not claim that the private model survives app deletion. Normal app updates retain app data; uninstalling removes it, so the exported copy is the recovery path. The model is not bundled in the APK or IPA.

The native inference bridge is vendored from iSyCode Móvil as a pinned, hash-verified snapshot, following TamagotchIA's `claude/gus-life-m1` approach. The initial source pin is `9c8a659840045cb31da7b501022645a194f4422d`; llama.cpp is pinned to `842b1880415d6f508f03b789e5ce70194def7bfd`. Generated vendor files are not edited by hand. Keep the upstream MIT notices and llama.cpp license notices with the vendored/build artifacts.

## User experience

- Add a GUS entry from Home that opens a dedicated chat and model controls without adding a sixth bottom-navigation tab.
- Start in **GUS local** mode. Show whether the native runtime is available, which model is selected, and whether setup is needed.
- Let the user download a model from a small, curated, immutable catalogue or import a `.gguf` from Files. Only catalogue entries with matching byte count and SHA-256 can be installed. Show the model's size, source, and license before download.
- Provide **Guardar copia**. On iOS, use the system Files export picker and copy the model. On Android, ask the user to choose a destination folder with the Storage Access Framework and copy the model there. Do not silently overwrite an existing copy; confirm replacement or choose a distinct filename.
- Provide **Importar** for one or more model files or a selected folder. Copy the selected model into app-private storage and verify it against the pinned catalogue before making it selectable. Explain rejected files and hash/size failures.
- Selecting **GUS remoto** is an explicit mode change. Configure an OpenAI-compatible HTTPS base URL, model name, and API key; show the chosen provider/model and explain that chat turns will be sent there before the first request. Store credentials in platform secure storage, send them only in the authorization header, and never log them or message bodies. Remote provider/setup errors remain visible; they do not switch to local or fallback automatically. Switching back to local is explicit.
- Keep chat messages in memory for the current app session only in M6.1. Do not add GUS messages to Link receipts, PC task history, or Tamagotchi state.

## Architecture

1. **Chat UI (`mobile/src`)** owns the current conversation, selected route, loading/cancel state, and setup/error messages. It calls a typed provider interface; it does not call native inference or remote HTTP directly.
2. **Local provider** composes the GUS system instruction and chat turns, then calls a Capacitor `GusLocal` plugin. The native boundary accepts text/messages and a catalogue model identifier, and returns generated text or a typed error. It cannot access Link keys, paired-PC records, permission leases, or arbitrary filesystem paths.
3. **Native runtime** integrates the pinned GUS C bridge and llama.cpp build in both iOS and Android. It confines model access to the app's private GUS model directory, loads one model/inference at a time, supports cancellation and unload, and caps context/output limits in native code as well as TypeScript.
4. **Model manager** downloads only catalogue-pinned HTTPS sources, validates allowed redirect hosts, caps size, stages partial files, verifies exact size and SHA-256, then atomically adopts the model. Import follows the same verification gate. Failed or cancelled partial files are never selectable.
5. **Backup and restore** use platform-owned file APIs. iOS uses security-scoped URLs and coordinated file access; Android uses SAF document/tree URIs and content streams. Treat the external copy as user-owned: never delete it when removing an in-app model. Re-import copies and revalidates it rather than trusting its filename or prior status.
6. **Remote provider** is a separate OpenAI-compatible HTTP provider. It receives only the active chat turns and the GUS system instruction. No Link/device metadata, local model contents, or TamagotchIA state is sent. The remote mode is never selected as a consequence of an error.

## Trust, privacy, and failure behavior

- Local means prompt inference stays on the phone. Model downloads and explicit backup/import are separate user-visible file/network operations.
- Remote mode discloses that chat text leaves the phone. It is opt-in and does not inherit prior local mode silently.
- GUS is advisory text only in M6.1. It has no tools, Link operation, filesystem capability, permission authority, or ability to execute commands.
- No model weights, provider key, or device-specific model diagnostics are uploaded. Chat is not persisted or sent anywhere while local mode is selected; only the active conversation is sent to the configured endpoint after the user explicitly selects remote mode.
- Missing runtime, missing/unreadable model, revoked file access, insufficient disk space, download/hash failure, timeout, cancellation, malformed provider response, or unavailable remote provider produces an actionable error. Do not change routes or erase the external backup to recover.
- App-private models survive ordinary app updates. App deletion removes the private model and app-held picker authorization; the external backup remains in its user-selected Files/shared-storage provider. After reinstall, ask the user to select the backup again if its prior authorization is unavailable, then re-import it.

## Scope boundaries

Included: GUS chat UI, native local inference on iOS and Android, pinned runtime provenance, curated model download/import/export, explicit local/remote mode selection, secure remote credentials, and CI/device validation.

Excluded: Tamagotchi creature state or memory (M7), chat-triggered Link actions, remote fallback, arbitrary unverified GGUF installation, background model downloads, model benchmarking/experiments, cross-device chat synchronization, and bundled model weights.

## Verification and evidence

- Unit tests cover route choice, explicit remote selection, and the invariant that local failure never issues a remote request.
- Model-manager tests cover catalogue pin validation, redirect/size limits, SHA-256 rejection, cancellation, import, export, and safe replacement behavior.
- A bridge contract test proves that the native plugin receives no Link secrets or filesystem path from the web layer.
- Mobile e2e covers Home → GUS, no-model setup, local/remote mode selection, and clear errors with a mocked native bridge/provider.
- CI verifies the vendored snapshot against its pinned source, builds the web bundle, Android APK and unsigned iOS IPA, and verifies that no `.gguf` is bundled.
- Native smoke tests on a physical iPhone and Android phone must separately demonstrate model download/import, local generation, export, reinstall/restore, and remote opt-in. CI compilation alone is not device evidence.

## References

- iSyCode Móvil model storage, import/export and provenance: `Sources/Model/GUSModelDownloadManager.swift`, `Sources/UI/GUSModelDownloadView.swift`, `android/.../gus/ModelStore.kt`, `android/.../GusViewModel.kt`, all at commit `9c8a659840045cb31da7b501022645a194f4422d`.
- TamagotchIA's pinned runtime vendoring decision: `docs/GUS_RUNTIME_VENDORING.md` on branch `claude/gus-life-m1`.
- IsyMotron mobile roadmap: `docs/mobile/ROADMAP.md`, M6.1.
