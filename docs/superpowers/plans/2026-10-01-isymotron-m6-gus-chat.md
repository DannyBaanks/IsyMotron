# IsyMotron M6.1 GUS Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a GUS chat in IsyMotron Móvil with local inference by default, verified model download/backup/restore, and remote inference only after explicit selection.

**Architecture:** A typed TypeScript chat/provider boundary routes to either a local Capacitor plugin or an OpenAI-compatible HTTPS provider. iOS and Android native plugins share the pinned iSyCode Móvil llama.cpp bridge, keep active models in app-private storage, and use system file pickers to export/import verified backups.

**Tech Stack:** TypeScript, Vite, Vitest, Capacitor 8, Java, Swift, C/C++, llama.cpp, Android NDK/CMake, Swift Package Manager, XCTest/JUnit, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-isymotron-m6-gus-chat-design.md`

## Global Constraints

- iOS deployment target remains iOS 15 or newer.
- GUS local is the default route; errors never trigger remote mode or another fallback.
- The runtime source pin is iSyCode Móvil `9c8a659840045cb31da7b501022645a194f4422d`; llama.cpp is `842b1880415d6f508f03b789e5ce70194def7bfd`.
- Keep the model catalogue in the app, immutable at runtime, with pinned source revision, exact byte count, SHA-256, attribution, and license.
- Native plugin methods accept catalogue model IDs, not arbitrary paths or download URLs; native code independently verifies model files.
- Keep GGUF weights, chat transcripts, and provider secrets out of APK/IPA assets and logs.
- Initial GUS generation limits are 2048 context tokens and 160 output tokens, matching the TamagotchIA reference branch.
- `GUS_SYSTEM_PROMPT` is identical for local and remote providers: “Eres GUS, asistente de IsyMotron. Responde en el idioma del usuario, de forma breve y clara. Solo das orientación: no tienes acceso a herramientas, Link, archivos, permisos ni a la PC enlazada. No afirmes haber ejecutado acciones. Si no sabes un dato, dilo.”
- Vendor/catalog generators may write only their named generated files; they must not recursively clear or replace a directory.
- Remote mode accepts an OpenAI-compatible HTTPS base URL, model, and API key; the API key is stored in iOS Keychain or Android Keystore-backed storage and sent only in the authorization header.
- Exported model copies are user-owned; deleting an in-app model must not delete an exported copy.
- Preserve unrelated pre-existing working-tree changes; commit only paths listed for each task.

## Review Focus

- PWA/browser or missing native plugin while local mode is selected: show local-unavailable guidance and make zero remote requests; test in `mobile/tests/gus-routing.test.ts` and the GUS e2e.
- Altered, oversized, truncated, redirected, or unlisted GGUF/download: reject it and leave no selectable partial model; test in `mobile/tests/gus-models.test.ts` and native model-store tests.
- User cancels or revokes access during import/export: retain the installed model and show a recoverable message; test import/export cancellation on both native plugin suites and GUS e2e.
- Remote endpoint is non-HTTPS, key invalid, HTTP error, timeout, or invalid JSON: show an error, do not include the key in request JSON/logs, and never change route; test in `mobile/tests/gus-remote.test.ts`.
- App is reinstalled, the backup was moved, or its external provider is unavailable: request a new picker selection or report a clear restore error without deleting the backup; test native restore handling and document the physical-device smoke procedure.

---

### Task 1: Define provider contracts and route policy

**Files:**
- Create: `mobile/src/gus/contracts.ts`
- Create: `mobile/src/gus/routing.ts`
- Test: `mobile/tests/gus-routing.test.ts`

**Interfaces:**
- Produce `GusMessage = { role: "system" | "user" | "assistant"; content: string }` and `GusProvider.complete(messages: readonly GusMessage[], signal?: AbortSignal): Promise<string>`.
- Produce `GUS_SYSTEM_PROMPT: string`, `GusMode = "local" | "remote"`, `GusRouteProviders = { local: GusProvider | null; remote: GusProvider | null }`, and `routeGus(mode: GusMode, providers: GusRouteProviders): GusProvider`; selected provider errors propagate to the caller without trying the other route.

- [ ] **Step 1: Write failing route tests** for local selection, remote selection, unavailable local plugin, missing remote configuration, and a local error that must not call the remote provider.
- [ ] **Step 2: Run** `cd mobile && npm test -- tests/gus-routing.test.ts`; confirm the tests fail because the route module is absent.
- [ ] **Step 3: Implement** the message/provider types, the exact `GUS_SYSTEM_PROMPT` from Global Constraints, and route selection in `mobile/src/gus/contracts.ts` and `mobile/src/gus/routing.ts`. Throw a typed `GusUnavailableError` if the selected provider is not configured.
- [ ] **Step 4: Run** `cd mobile && npm test -- tests/gus-routing.test.ts`; expect all route tests to pass.
- [ ] **Step 5: Commit** only these files as `feat: define GUS provider routing`.

### Task 2: Pin the runtime and generate the model catalogue

**Files:**
- Create: `mobile/vendor/gus-runtime/Sources/Model/GUSLlamaBridge.c`
- Create: `mobile/vendor/gus-runtime/Sources/Model/GUSLlamaBridge.h`
- Create: `mobile/vendor/gus-runtime/scripts/build-llama-xcframework.sh`
- Create: `mobile/vendor/gus-runtime/VENDOR.json`, `README.md`, and upstream MIT `LICENSE`
- Create: `mobile/vendor/gus-runtime/LLAMA_CPP_LICENSE.txt` and its SHA-256 entry in `VENDOR.json`
- Create: `mobile/catalog/gus-models.json`
- Create: `mobile/tools/sync-gus-runtime.mjs`
- Create: `mobile/tools/generate-gus-catalog.mjs`
- Create: `mobile/src/gus/catalog.generated.ts`
- Create: `mobile/tests/gus-catalog.test.ts`
- Create: `mobile/tests/gus-models.test.ts`
- Create: `mobile/tests/gus-runtime-vendor.test.ts`

**Interfaces:**
- `sync-gus-runtime.mjs --verify` checks the exact pinned source bytes and manifest without network; `--check` additionally regenerates from the pin and compares the snapshot. The writer updates only its allowlisted files and never recursively removes its destination.
- `generate-gus-catalog.mjs` generates `catalog.generated.ts` from `catalog/gus-models.json`; that JSON is the sole model metadata source used to generate native catalogue files in Tasks 3 and 4.
- Each model entry has `id`, `name`, `repository`, `filename`, 40-hex `revision`, `url`, `byteCount`, 64-hex `sha256`, `licenseName`, `licenseUrl`, and `attribution`. Start with the two sub-500-MB Apache-licensed entries pinned in iSyCode Móvil: `qwen25-05b-q4km` and `smollm2-360m-q4km`.
- `mobile/tests/gus-models.test.ts` proves UI-facing catalogue lookup returns only those pinned IDs and exposes exact size, source, attribution, and license metadata; acceptance of actual files remains native.
- Include upstream `LICENSE` in the sync allowlist and manifest so the MIT notice is reproducible along with the bridge source.
- Fetch llama.cpp's `LICENSE` from commit `842b1880415d6f508f03b789e5ce70194def7bfd` and verify its hash before adding it to the vendor manifest.

- [ ] **Step 1: Write failing tests** for each source hash, manifest pin, exact generated catalogue output, and rejection of malformed SHA, mutable `main`/`latest` revisions, non-HTTPS URLs, and duplicate model IDs; add the pinned-ID/metadata assertions to `gus-models.test.ts`.
- [ ] **Step 2: Run** `cd mobile && npm test -- tests/gus-catalog.test.ts tests/gus-models.test.ts tests/gus-runtime-vendor.test.ts`; confirm the new test files fail before implementation.
- [ ] **Step 3: Implement** the fixed-pin vendor sync and catalogue generator using the verified upstream allowlist. Preserve the upstream MIT notice and the llama.cpp license notice in build/distribution artifacts.
- [ ] **Step 4: Run** `cd mobile && npm test -- tests/gus-catalog.test.ts tests/gus-models.test.ts tests/gus-runtime-vendor.test.ts && node tools/sync-gus-runtime.mjs --verify && node tools/generate-gus-catalog.mjs --check`; expect all checks to pass.
- [ ] **Step 5: Commit** only vendor, catalogue, generator, and test files as `vendor: pin GUS runtime and model catalog`.

### Task 3: Build the Android local-runtime and model plugin

**Files:**
- Create: `mobile/android/app/src/main/cpp/CMakeLists.txt`
- Create: `mobile/android/app/src/main/cpp/gus_jni.c`
- Create: `mobile/android/app/src/main/java/io/github/dannybaanks/isymotron/GusLocalPlugin.java`
- Create: `mobile/android/app/src/main/java/io/github/dannybaanks/isymotron/GusModelStore.java`
- Create: `mobile/android/app/src/main/java/io/github/dannybaanks/isymotron/GusSecretsPlugin.java`
- Modify: `mobile/android/app/build.gradle`
- Modify: `mobile/android/app/src/main/java/io/github/dannybaanks/isymotron/MainActivity.java`
- Test: `mobile/android/app/src/test/java/io/github/dannybaanks/isymotron/GusModelStoreTest.java`
- Test: `mobile/android/app/src/androidTest/java/io/github/dannybaanks/isymotron/GusLocalPluginTest.java`
- Modify: `mobile/tools/generate-gus-catalog.mjs` (emit `GusCatalog.java`)
- Create: `mobile/android/app/src/main/java/io/github/dannybaanks/isymotron/GusCatalog.java` (generated)

**Interfaces:**
- Register `GusLocalPlugin` (Capacitor name `GusLocal`) and `GusSecretsPlugin` (Capacitor name `GusSecrets`) before `BridgeActivity` starts.
- `GusLocalPlugin` exposes `listModels()`, `downloadModel({modelId})`, `cancelDownload({modelId})`, `importModels()`, `exportModel({modelId})`, `generate({modelId,messages,contextTokens,maxTokens})`, `cancel()`, and `unload()`; import/export launch Android system pickers and download progress is emitted as `downloadProgress`.
- `GusModelStore` resolves IDs against generated `GusCatalog`, downloads only pinned HTTPS URLs, verifies exact bytes and SHA-256, stores active models under `filesDir/gus/models`, and imports/exports via `ContentResolver` streams and SAF URIs.
- `GusSecretsPlugin` exposes `getRemoteConfig(): Promise<{baseUrl:string;model:string}|null>`, `saveRemoteConfig({baseUrl,model})`, `getApiKey(): Promise<string|null>`, `saveApiKey({apiKey})`, and `clearRemoteConfig()`; encrypt the key with a key held by Android Keystore.

- [ ] **Step 1: Write failing JUnit tests** for model ID lookup, valid file adoption, bad size/hash, oversized payload, untrusted redirect, partial-file cleanup, cancelled/revoked SAF access preserving installed files, and restoring an exported catalogue model into a fresh store instance.
- [ ] **Step 2: Run** `cd mobile/android && ./gradlew :app:testDebugUnitTest`; confirm the new model-store tests fail before the store exists.
- [ ] **Step 3: Implement** the pure-Java store and generated static catalogue, then wire picker-based import/export, pinned HTTPS downloads, `cancelDownload`, and `downloadProgress` into `GusLocalPlugin`.
- [ ] **Step 4: Add the NDK/CMake build** using the llama.cpp SHA in `VENDOR.json`, compile the pinned C bridge plus JNI shim for `arm64-v8a`, set native model/output caps, cancellation, and unload; wire app Gradle and plugin registration.
- [ ] **Step 5: Add Keystore-backed credential CRUD** and instrumentation tests proving the plugin is registered, a user-cancelled or revoked SAF picker does not alter installed models, and native runtime absence is reported as an error.
- [ ] **Step 6: Run** `cd mobile/android && ./gradlew :app:testDebugUnitTest :app:assembleDebug`; expect unit tests and the arm64 debug APK build to pass.
- [ ] **Step 7: Commit** only Android plugin, runtime/build, generated catalogue, and tests as `feat: add Android GUS runtime`.

### Task 4: Build the iOS local-runtime and model plugin

**Files:**
- Create: `mobile/ios/App/GusLocal/Package.swift`
- Create: `mobile/ios/App/GusLocal/prepare.sh`
- Create: `mobile/ios/App/GusLocal/Sources/GUSBridge/GUSLlamaBridge.c` (symlink to pinned vendor source)
- Create: `mobile/ios/App/GusLocal/Sources/GUSBridge/include/GUSLlamaBridge.h` (symlink to pinned vendor header)
- Create: `mobile/ios/App/GusLocal/Sources/GusModelStore/GusModelStore.swift`
- Create: `mobile/ios/App/GusLocal/Sources/GusLocalPlugin/GusLocalPlugin.swift`
- Create: `mobile/ios/App/GusLocal/Sources/GusLocalPlugin/GusSecretsPlugin.swift`
- Create: `mobile/ios/App/GusLocal/Tests/GusModelStoreTests/GusModelStoreTests.swift`
- Create: `mobile/ios/App/GusLocal/.gitignore`
- Modify: `mobile/ios/App/App.xcodeproj/project.pbxproj`
- Modify: `mobile/tools/generate-gus-catalog.mjs` (emit `GUSCatalog.generated.swift`)
- Create: `mobile/ios/App/GusLocal/Sources/GusLocalPlugin/GUSCatalog.generated.swift` (generated)

**Interfaces:**
- Register `GusLocalPlugin` (Capacitor name `GusLocal`) and `GusSecretsPlugin` (Capacitor name `GusSecrets`) with the same method names and JSON contract as Task 3, including `cancelDownload({modelId})` and the `downloadProgress` listener event.
- `GusLocalPlugin` stores models under app-private `Application Support/IsyMotron/GUS/Models`, and uses `UIDocumentPickerViewController` for import/export; external file access uses security-scoped URLs and coordinated reads/writes.
- `GusSecretsPlugin` exposes the same credential methods as Android and stores the API key in Keychain.
- `GusModelStore` is a Foundation-only target used by the Capacitor plugin and the macOS XCTest target; it receives file URLs/manifests from the fixed catalogue and performs staged, hash-verified adoption.

- [ ] **Step 1: Write failing Swift package tests** for manifest-only model IDs, hash/size rejection, safe import, failed staged copy preserving an existing model, cancelled or denied security-scoped access leaving the store unchanged, restoring a catalogue model into a fresh store instance, and credential CRUD through an injectable keychain adapter.
- [ ] **Step 2: Run on macOS** `cd mobile/ios/App/GusLocal && swift test`; confirm the store tests fail before implementation.
- [ ] **Step 3: Implement** the SwiftPM package and plugin around the pinned C bridge; add picker import/export with security-scoped access and verified atomic installation under Application Support.
- [ ] **Step 4: Add Keychain-backed credential CRUD** and set native generation limits to 2048 context tokens and 160 output tokens.
- [ ] **Step 5: Link the local package** from `App.xcodeproj/project.pbxproj`; run `cd mobile/ios/App/GusLocal && swift test` and expect all Foundation-only package tests to pass on macOS.
- [ ] **Step 6: Run** the mobile iOS CI build command (`npx cap sync ios`, build pinned `llama.xcframework`, then `xcodebuild` for unsigned device IPA); expect the native package, plugin, and bridge to link into the app.
- [ ] **Step 7: Commit** only iOS plugin/package/project/generated catalogue/tests as `feat: add iOS GUS runtime`.

### Task 5: Implement remote provider and no-fallback semantics

**Files:**
- Create: `mobile/src/gus/remote.ts`
- Create: `mobile/src/gus/credentials.ts`
- Create: `mobile/tests/gus-remote.test.ts`
- Modify: `mobile/src/gus/routing.ts`

**Interfaces:**
- `GusRemoteConfig = { baseUrl: string; model: string }`; API key is retrieved from the native secure-store interface and is never part of this public config type. `contracts.ts` also exports one `GUS_SYSTEM_PROMPT` used by both providers.
- `GusSecureStore` exposes `getRemoteConfig(): Promise<GusRemoteConfig | null>`, `saveRemoteConfig(config: GusRemoteConfig): Promise<void>`, `getApiKey(): Promise<string | null>`, `saveApiKey(apiKey: string): Promise<void>`, and `clearRemoteConfig(): Promise<void>`.
- `createRemoteProvider` receives `getApiKey: () => Promise<string | null>`; the native secure-store plugin returns the key only to the current trusted app process, never to localStorage or the request body.
- `createRemoteProvider(config, getApiKey, fetcher = fetch): GusProvider` posts `model`, `max_tokens: 160`, and the system prompt plus active conversation to `<baseUrl>/chat/completions`; `baseUrl` must be HTTPS and have no embedded credentials/query/fragment.
- Responses are read from `choices[0].message.content`; status, timeout, absent content, and malformed JSON throw typed user-facing errors.

- [ ] **Step 1: Write failing tests** for a valid response containing only the active conversation and system prompt, no key in the body or logs, key only in `Authorization`, rejection of HTTP/non-HTTPS endpoints and embedded URL credentials, 401/429/5xx, timeout, malformed JSON, and no call to local when remote is selected but fails.
- [ ] **Step 2: Run** `cd mobile && npm test -- tests/gus-remote.test.ts tests/gus-routing.test.ts`; verify the remote tests fail first.
- [ ] **Step 3: Implement** URL/config validation, secure-store adapter calls, abortable fetch, response parsing, and typed errors; do not add route fallback.
- [ ] **Step 4: Run** the same Vitest command and `cd mobile && npm run check`; expect all tests and TypeScript checking to pass.
- [ ] **Step 5: Commit** only remote provider, routing change, and tests as `feat: add explicit GUS remote provider`.

### Task 6: Add GUS chat and model controls to the mobile UI

**Files:**
- Create: `mobile/src/gus/native.ts`
- Create: `mobile/src/gus/chat.ts`
- Create: `mobile/src/gus/chat.testable.ts` (pure view-state transitions only)
- Test: `mobile/tests/gus-chat.test.ts`
- Test: `mobile/tests/gus-native-boundary.test.ts`
- Modify: `mobile/src/home.ts`
- Modify: `mobile/src/main.ts`
- Modify: `mobile/src/styles.css`

**Interfaces:**
- `native.ts` wraps Capacitor `GusLocal` and `GusSecrets` with the exact plugin methods from Tasks 3–4 and exposes `isNativeGusAvailable()`.
- `GusChatController` exposes `getState(): GusChatState`, `subscribe(listener: (state: GusChatState) => void): () => void`, `send(text: string): Promise<void>`, `cancel(): Promise<void>`, `selectMode(mode: GusMode): void`, `downloadModel(id: string): Promise<void>`, `importModels(): Promise<void>`, `exportModel(id: string): Promise<void>`, and `clearSession(): void`. `createGusChat(deps)` accepts the local/remote providers, model catalogue, and secure config adapter and returns this controller.
- `GusAppDeps = { local: GusProvider | null; remoteConfig: GusRemoteConfig | null; secureStore: GusSecureStore; catalogue: readonly GusModelManifest[] }`. `createGusChat` builds the remote provider from `remoteConfig` and `secureStore`; `startApp` receives `gus: GusAppDeps` through `AppDeps`; Home shows a **GUS** entry, and `gusScreen()` renders without adding a bottom-navigation tab.

- [x] **Step 1: Write failing tests** for blank-message rejection, session-only turns, abort-signal calling native `cancel()`, loading/cancel state, selected mode persistence for the session, model setup/import/export outcomes, and no route change after provider failure; add a native-boundary contract test proving only model ID, message strings, and fixed generation limits cross the Capacitor bridge, with no Link keys, leases, or file path.
- [x] **Step 2: Run** `cd mobile && npm test -- tests/gus-chat.test.ts`; confirmed the missing controller and native wrapper failed before implementation.
- [x] **Step 3: Implement** the testable chat controller and Capacitor wrappers; serialize only approved local-plugin fields, show native-unavailable state on browser/PWA, and do not trigger remote automatically.
- [x] **Step 4: Add the Home entry and GUS screen** with chat composer, local/remote selector, model catalogue with size/source/license, progress/cancel, import/export, remote HTTPS configuration, and explicit remote-data notice.
- [x] **Step 5: Add styles** consistent with Verde terminal and accessible button labels, live progress/error announcements, and keyboard focus behavior.
- [x] **Step 6: Run** `cd mobile && npm test && npm run build`; 14 files / 70 tests passed and the production TypeScript/Vite build completed.
- [x] **Step 7: Commit** only GUS TypeScript/UI/CSS/tests as `feat: add GUS chat to mobile home`.

### Task 7: Add native CI, end-to-end coverage, and the operator guide

**Files:**
- Modify: `.github/workflows/mobile.yml`
- Create: `.github/workflows/gus-runtime.yml`
- Create: `mobile/e2e/gus.e2e.mjs`
- Create: `mobile/tests/gus-e2e-isolation.test.ts`
- Create: `mobile/src/gus/e2e-mock.ts` (included only in Vite `e2e` mode)
- Modify: `mobile/package.json` (add `build:e2e` and `e2e:gus` scripts)
- Create: `docs/mobile/GUS_GUIDE.md`

- [x] **Step 1: Write a failing Playwright flow** that visits Home → GUS, sees local model setup, selects local/remote explicitly, exercises mocked model download/import/export, and verifies a failed local request never makes a mocked remote request.
- [x] **Step 2: Add** `build:e2e` (`tsc --noEmit && vite build --mode e2e`) and `e2e:gus` (`npm run build:e2e && node e2e/gus.e2e.mjs`) scripts to `mobile/package.json`; the flow initially stopped at missing Chromium, then passed after installing the test browser.
- [x] **Step 3: Implement** the mock-plugin/provider test seam in `src/gus/e2e-mock.ts`, loaded only when `import.meta.env.MODE === "e2e"`; add a production build assertion that `dist/assets` contains no e2e mock marker.
- [x] **Step 4: Extend mobile CI** to run vendor verification, catalog generation check, Android JVM tests/APK assembly, iOS Swift package tests, pinned XCFramework build and unsigned IPA build; inspect each artifact to confirm no `.gguf` is bundled.
- [x] **Step 5: Add** `docs/mobile/GUS_GUIDE.md` with model download/import/export/restore steps, remote setup and data-egress explanation, exact test/build commands, representative real output from validation, and recovery steps for cancelled/revoked file-picker access.
- [ ] **Step 6: Run** `cd mobile && npm test && npm run build && npm run e2e:gus`; run the native Gradle and Xcode workflow commands; expect the web/e2e suites and both native package builds to pass. Web suite, production build, GUS E2E, and existing Link E2E pass locally; Android NDK and Xcode commands are configured in CI but remain NOT_DEMONSTRATED on this Linux host.
- [x] **Step 7: Record physical-device evidence** only after testing a real iPhone and Android phone: local generation offline, backup export, app removal/reinstall, restore, and remote opt-in. No physical device run is claimed; these cases remain `NOT_DEMONSTRATED`.
- [x] **Step 8: Commit** only workflow, e2e, package-script, and guide files as `test: verify GUS mobile flows and builds`.

## Execution Notes

- Run tasks in order; each task consumes the prior task's interfaces.
- Before implementation, create an isolated worktree from the approved spec commit using `superpowers:using-git-worktrees`; keep the user's existing dirty working-tree changes untouched.
- Use `superpowers:test-driven-development` for code tasks and `superpowers:verification-before-completion` before claiming completion.
- Never commit generated `.gguf`, `.xcframework`, llama.cpp checkout/build output, secrets, or user chat text.
- Native app CI builds prove compilation/package contents only. Physical inference and reinstall/restore remain unproven until run on actual devices.
