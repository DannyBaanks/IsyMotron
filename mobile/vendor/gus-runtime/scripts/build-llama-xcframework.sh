#!/usr/bin/env bash
set -euo pipefail

readonly LLAMA_REPOSITORY="https://github.com/ggml-org/llama.cpp.git"
readonly LLAMA_COMMIT="842b1880415d6f508f03b789e5ce70194def7bfd"
readonly VENDOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BUILD_ROOT="${ISYMOTRON_LLAMA_BUILD_DIR:-${TMPDIR:-/tmp}/isymotron-gus-llama-${LLAMA_COMMIT}}"
readonly SOURCE_DIR="${BUILD_ROOT}/source"
readonly OUTPUT_DIR="${VENDOR_ROOT}/../../ios/App/.build/gus-runtime"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "llama.xcframework requires macOS and Xcode." >&2
  exit 2
fi
command -v cmake >/dev/null || { echo "cmake is required" >&2; exit 2; }
command -v xcrun >/dev/null || { echo "Xcode Command Line Tools are required" >&2; exit 2; }

if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
  mkdir -p "${BUILD_ROOT}"
  git clone --filter=blob:none --no-checkout "${LLAMA_REPOSITORY}" "${SOURCE_DIR}"
fi
git -C "${SOURCE_DIR}" fetch --depth 1 origin "${LLAMA_COMMIT}"
git -C "${SOURCE_DIR}" checkout --detach "${LLAMA_COMMIT}"
actual="$(git -C "${SOURCE_DIR}" rev-parse HEAD)"
[[ "${actual}" == "${LLAMA_COMMIT}" ]] || { echo "Unexpected llama.cpp revision: ${actual}" >&2; exit 1; }

cd "${SOURCE_DIR}"
./build-xcframework.sh ios-device ios-sim
mkdir -p "${OUTPUT_DIR}"
if [[ -e "${OUTPUT_DIR}/llama.xcframework" ]]; then
  echo "Output already exists at ${OUTPUT_DIR}/llama.xcframework; move it aside before rebuilding." >&2
  exit 2
fi
cp -R "${SOURCE_DIR}/build-apple/llama.xcframework" "${OUTPUT_DIR}/llama.xcframework"
printf '%s\n' "${actual}" > "${OUTPUT_DIR}/SOURCE_COMMIT"
