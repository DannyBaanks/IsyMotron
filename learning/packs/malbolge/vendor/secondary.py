"""Independent classic runner copied from malbolge-anchuring.

Kept as a separate implementation for the L8 differential lesson. It has no
imports from the primary oracle; provenance is recorded in the pack receipt.
"""
from __future__ import annotations

MEMORY_SIZE = 3 ** 10
EOF_VALUE = 59048
_CRAZY = ((1, 0, 0), (1, 0, 2), (2, 2, 1))
_ORIGINAL = '!"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
_TRANSLATED = '5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK\'X~xDl}REokN:#?G"i@'
_ENCRYPT = dict(zip(map(ord, _ORIGINAL), map(ord, _TRANSLATED)))
_VALID = frozenset({4, 5, 23, 39, 40, 62, 68, 81})


def crazy(a: int, b: int) -> int:
    result = 0
    place = 1
    for _ in range(10):
        result += _CRAZY[b % 3][a % 3] * place
        a //= 3
        b //= 3
        place *= 3
    return result


def run(source: str, stdin_data: bytes = b"", max_steps: int = 2_000_000):
    chars = [c for c in source if not c.isspace()]
    if len(chars) > MEMORY_SIZE:
        return "INVALID", 0, b""
    mem = [0] * MEMORY_SIZE
    for i, ch in enumerate(chars):
        if not 33 <= ord(ch) <= 126 or (ord(ch) + i) % 94 not in _VALID:
            return "INVALID", 0, b""
        mem[i] = ord(ch)
    for i in range(len(chars), MEMORY_SIZE):
        mem[i] = crazy(mem[i - 1], mem[i - 2])
    a = c = d = pos = 0
    out = bytearray()
    while pos < max_steps:
        pos += 1
        instruction = (mem[c] + c) % 94
        if instruction == 4: c = mem[d]
        elif instruction == 5: out.append(a % 256)
        elif instruction == 23:
            a = stdin_data[0] if stdin_data else EOF_VALUE
            stdin_data = stdin_data[1:]
        elif instruction == 39:
            mem[d] = mem[d] // 3 + (mem[d] % 3) * 3 ** 9; a = mem[d]
        elif instruction == 40: d = mem[d]
        elif instruction == 62: mem[d] = a = crazy(a, mem[d])
        elif instruction == 81: return "HALTED", pos, bytes(out)
        if 33 <= mem[c] <= 126: mem[c] = _ENCRYPT[mem[c]]
        c = (c + 1) % MEMORY_SIZE; d = (d + 1) % MEMORY_SIZE
    return "OUT_OF_FUEL", pos, bytes(out)
