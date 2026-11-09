#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "rng.hpp"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

#if defined(__linux__) && !defined(__ANDROID__)
#include <sys/random.h>
#define RNG_USE_GETRANDOM 1
#else
#define RNG_USE_ARC4RANDOM 1
#endif

// ALT_RNG_REV_0 -- leaf file used by the incremental edit test.

namespace {

constexpr std::size_t kBufferSize = 4096;

// All implementations read the system CSPRNG through the same 4096-byte
// buffer and consume little-endian 32-bit words. This keeps the random-value
// consumption pattern identical across languages; only the OS call used to
// fill the buffer differs.
//
// The buffer and offset are fixed-size globals, matching Zig: no allocation,
// refill only when fewer than four bytes remain, and no fallback PRNG.
unsigned char rng_buffer[kBufferSize];
std::size_t rng_offset = kBufferSize;

void rng_fill(void *buffer, std::size_t len) {
#if defined(RNG_USE_GETRANDOM)
  auto *cursor = static_cast<unsigned char *>(buffer);
  std::size_t remaining = len;

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
    remaining -= static_cast<std::size_t>(got);
  }
  if (remaining == 0) {
    return;
  }
#else
  arc4random_buf(buffer, len);
  return;
#endif

  std::fputs("passgen: CSPRNG failure\n", stderr);
  std::exit(2);
}

void rng_refill() {
  rng_fill(rng_buffer, sizeof rng_buffer);
  rng_offset = 0;
}

std::uint32_t rng_next_u32() {
  if (rng_offset + 4 > kBufferSize) {
    rng_refill();
  }

  const unsigned char *bytes = rng_buffer + rng_offset;
  rng_offset += 4;
  return static_cast<std::uint32_t>(bytes[0]) |
         (static_cast<std::uint32_t>(bytes[1]) << 8) |
         (static_cast<std::uint32_t>(bytes[2]) << 16) |
         (static_cast<std::uint32_t>(bytes[3]) << 24);
}

} // namespace

std::size_t rng_below(std::size_t n) {
  if (n <= 1) {
    return 0;
  }

  const std::uint64_t limit =
      ((static_cast<std::uint64_t>(1) << 32) / n) * n;
  for (;;) {
    std::uint32_t value = rng_next_u32();
    if (static_cast<std::uint64_t>(value) < limit) {
      return static_cast<std::size_t>(value % n);
    }
  }
}
