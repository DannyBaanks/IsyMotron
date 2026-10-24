"""Shared probe for Linux tool-provider tests.

The provider needs bubblewrap with working user namespaces. Some CI hosts
disable unprivileged user namespaces, so the integration tests probe the
real binary instead of assuming that "Linux" is enough.
"""
from __future__ import annotations

import shutil
import subprocess


def bwrap_works() -> bool:
    binary = shutil.which('bwrap')
    if not binary:
        return False
    try:
        result = subprocess.run(
            [binary, '--unshare-all', '--share-net', '--ro-bind', '/', '/', '/bin/true'],
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
