# GUS native runtime provenance

This directory contains a byte-pinned snapshot of `GUSLlamaBridge.c`, its header, and the upstream iSyCode Móvil MIT license from commit `9c8a659840045cb31da7b501022645a194f4422d`. The bridge links against llama.cpp commit `842b1880415d6f508f03b789e5ce70194def7bfd`, distributed under the preserved `LLAMA_CPP_LICENSE.txt` notice.

Run `node mobile/tools/sync-gus-runtime.mjs --verify` from the repository root to verify local bytes without network. `--check` additionally compares every allowlisted snapshot file with its pinned upstream raw source. `--sync` downloads only those allowlisted files and replaces them only after every fetched byte sequence matches its fixed SHA-256.

`mobile/vendor/gus-runtime/scripts/build-llama-xcframework.sh` builds the pinned upstream XCFramework on macOS. Build products and downloaded llama.cpp sources remain outside tracked application assets; no model weights are bundled.
