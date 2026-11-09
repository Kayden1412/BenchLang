"""System CSPRNG wrapper (ALT_RNG_REV_0 -- leaf file for the edit test).

All implementations read the system CSPRNG through the same 4096-byte buffer
and consume little-endian 32-bit words. This keeps the random-value consumption
pattern identical across languages; only the OS call used to fill the buffer
differs.

The buffer and offset are fixed-size state, matching Zig: the bytearray is
reused and refilled only when fewer than four bytes remain.
"""

import secrets

BUFFER_SIZE = 4096

_buffer = bytearray(BUFFER_SIZE)
_offset = BUFFER_SIZE


def _refill() -> None:
    global _offset

    _buffer[:] = secrets.token_bytes(BUFFER_SIZE)
    _offset = 0


def _next_u32() -> int:
    global _offset

    if _offset + 4 > BUFFER_SIZE:
        _refill()

    value = int.from_bytes(memoryview(_buffer)[_offset : _offset + 4], "little")
    _offset += 4
    return value


def below(n: int) -> int:
    """Uniform integer in [0, n), using the OS cryptographic random source."""
    if n <= 1:
        return 0

    limit = ((1 << 32) // n) * n
    while True:
        value = _next_u32()
        if value < limit:
            return value % n
