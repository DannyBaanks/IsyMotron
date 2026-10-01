#!/usr/bin/env bash
set -euo pipefail
readonly LLAMA_REPOSITORY="https://github.com/ggml-org/llama.cpp.git"
readonly LLAMA_COMMIT="842b1880415d6f508f03b789e5ce70194def7bfd"
readonly VENDOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SOURCE_DIR="${1:-${VENDOR_ROOT}/.build/llama.cpp}"
if [[ -d "${SOURCE_DIR}/.git" ]]; then
  actual="$(git -C "${SOURCE_DIR}" rev-parse HEAD)"
  if [[ "${actual}" != "${LLAMA_COMMIT}" ]]; then
    echo "Existing llama.cpp source is ${actual}, expected ${LLAMA_COMMIT}; preserve it and choose another destination." >&2
    exit 2
  fi
else
  if [[ -e "${SOURCE_DIR}" ]]; then echo "Refusing to replace existing non-Git path: ${SOURCE_DIR}" >&2; exit 2; fi
  mkdir -p "$(dirname "${SOURCE_DIR}")"
  git clone --filter=blob:none --no-checkout "${LLAMA_REPOSITORY}" "${SOURCE_DIR}"
  git -C "${SOURCE_DIR}" fetch --depth 1 origin "${LLAMA_COMMIT}"
  git -C "${SOURCE_DIR}" checkout --detach "${LLAMA_COMMIT}"
fi
actual="$(git -C "${SOURCE_DIR}" rev-parse HEAD)"
[[ "${actual}" == "${LLAMA_COMMIT}" ]] || { echo "Unexpected llama.cpp revision: ${actual}" >&2; exit 1; }
printf '%s\n' "${SOURCE_DIR}"
