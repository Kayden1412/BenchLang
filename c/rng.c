#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "rng.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(__linux__) && !defined(__ANDROID__)
#include <sys/random.h>
#define RNG_USE_GETRANDOM 1
#else
#define RNG_USE_ARC4RANDOM 1
#endif

/* ALT_RNG_REV_0 -- leaf file used by the incremental edit test. */

#define RNG_BUFFER_SIZE 4096

/*
 * All implementations read the system CSPRNG through the same 4096-byte
 * buffer and consume little-endian 32-bit words. This keeps the random-value
 * consumption pattern identical across languages; only the OS call used to
 * fill the buffer differs.
 *
 * The buffer and offset are fixed-size globals, matching Zig: no allocation,
 * refill only when fewer than four bytes remain, and no fallback PRNG.
 */
static unsigned char rng_buffer[RNG_BUFFER_SIZE];
static size_t rng_offset = RNG_BUFFER_SIZE;

static void rng_fill(void *buffer, size_t len) {
#if defined(RNG_USE_GETRANDOM)
  unsigned char *cursor = (unsigned char *)buffer;
  size_t remaining = len;

  while (remaining > 0) {
    ssize_t got = getrandom(cursor, remaining, 0);
    if (got < 0) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    if (got == 0) {
      break;
    }
    cursor += got;
    remaining -= (size_t)got;
  }
  if (remaining == 0) {
    return;
  }
#else
  arc4random_buf(buffer, len);
  return;
#endif

  fputs("passgen: CSPRNG failure\n", stderr);
  exit(2);
}

static void rng_refill(void) {
  rng_fill(rng_buffer, sizeof rng_buffer);
  rng_offset = 0;
}

static uint32_t rng_next_u32(void) {
  if (rng_offset + 4 > RNG_BUFFER_SIZE) {
    rng_refill();
  }

  const unsigned char *bytes = rng_buffer + rng_offset;
  rng_offset += 4;
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
         ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

size_t rng_below(size_t n) {
  if (n <= 1) {
    return 0;
  }

  const uint64_t limit = (((uint64_t)1 << 32) / n) * n;
  for (;;) {
    uint32_t value = rng_next_u32();
    if ((uint64_t)value < limit) {
      return (size_t)(value % n);
    }
  }
}
