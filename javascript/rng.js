'use strict';

// ALT_RNG_REV_0 -- leaf file used by the incremental edit test.
//
// All implementations read the system CSPRNG through the same 4096-byte buffer
// and consume little-endian 32-bit words. This keeps the random-value
// consumption pattern identical across languages; only the OS call used to fill
// the buffer differs. There is no seeded PRNG and no Math.random() anywhere in
// this program.
//
// The buffer and offset are fixed-size state, matching Zig: no allocation,
// refill only when fewer than four bytes remain.

const { randomFillSync } = require('node:crypto');

const BUFFER_SIZE = 4096;

const buffer = Buffer.allocUnsafe(BUFFER_SIZE);
let offset = BUFFER_SIZE;

function nextU32() {
  if (offset + 4 > BUFFER_SIZE) {
    randomFillSync(buffer);
    offset = 0;
  }

  const value = buffer.readUInt32LE(offset);
  offset += 4;
  return value;
}

function below(n) {
  if (n <= 1) {
    return 0;
  }

  const limit = Math.floor(0x100000000 / n) * n;
  for (;;) {
    const value = nextU32();
    if (value < limit) {
      return value % n;
    }
  }
}

module.exports = { below };
