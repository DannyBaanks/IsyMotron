#!/usr/bin/env bash
set -euo pipefail
readonly LLAMA_COMMIT="842b1880415d6f508f03b789e5ce70194def7bfd"
readonly VENDOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SOURCE_DIR="$("${VENDOR_ROOT}/scripts/prepare-llama-source.sh" "${VENDOR_ROOT}/.build/llama.cpp")"
readonly OUTPUT_DIR="${VENDOR_ROOT}/../../ios/App/.build/gus-runtime"
if [[ "$(uname -s)" != "Darwin" ]]; then echo "llama.xcframework requires macOS and Xcode." >&2; exit 2; fi
command -v cmake >/dev/null || { echo "cmake is required" >&2; exit 2; }
command -v xcrun >/dev/null || { echo "Xcode Command Line Tools are required" >&2; exit 2; }
cd "${SOURCE_DIR}"
./build-xcframework.sh ios-device ios-sim
mkdir -p "${OUTPUT_DIR}"
if [[ -e "${OUTPUT_DIR}/llama.xcframework" ]]; then echo "Output already exists at ${OUTPUT_DIR}/llama.xcframework; choose a fresh build directory." >&2; exit 2; fi
cp -R "${SOURCE_DIR}/build-apple/llama.xcframework" "${OUTPUT_DIR}/llama.xcframework"
printf '%s\n' "${LLAMA_COMMIT}" > "${OUTPUT_DIR}/SOURCE_COMMIT"
