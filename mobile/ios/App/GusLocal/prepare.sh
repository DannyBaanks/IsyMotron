#!/usr/bin/env bash
set -euo pipefail
readonly PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_ROOT="$(cd "${PACKAGE_ROOT}/.." && pwd)"
readonly VENDOR_ROOT="$(cd "${APP_ROOT}/../../vendor/gus-runtime" && pwd)"
node "${APP_ROOT}/../../tools/sync-gus-runtime.mjs" --verify
"${VENDOR_ROOT}/scripts/build-llama-xcframework.sh"
readonly LLAMA_SOURCE="${VENDOR_ROOT}/.build/llama.cpp"
readonly SHIM_ROOT="${APP_ROOT}/.build/gus-runtime/shim/llama"
mkdir -p "${SHIM_ROOT}"
cp "${LLAMA_SOURCE}/include/llama.h" "${SHIM_ROOT}/llama.h"
printf 'Prepared pinned llama.cpp source and iOS XCFramework.\n'
