#define _GNU_SOURCE
#include "rng.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>

#include <fcntl.h>
#include <unistd.h>

#if defined(__ANDROID__)
#include <stdlib.h>
#elif defined(__linux__)
#include <sys/random.h>
#endif

// ALT_RNG_REV_0 -- leaf file used by the incremental edit test.

namespace {

constexpr std::size_t kBufferSize = 4096;

// All implementations read the system CSPRNG through the same 4096-byte
// buffer and consume little-endian 32-bit words. This keeps the random-value
// consumption pattern identical across languages; only the OS call used to
// fill the buffer differs.
unsigned char rng_buffer[kBufferSize];
std::size_t rng_offset = kBufferSize;

bool read_urandom(void *buffer, std::size_t len) {
  int fd = open("/dev/urandom", O_RDONLY);
  if (fd < 0) {
    return false;
  }

  auto *cursor = static_cast<unsigned char *>(buffer);
  while (len > 0) {
    ssize_t got = read(fd, cursor, len);
    if (got < 0) {
      if (errno == EINTR) {
        continue;
      }
      close(fd);
      return false;
    }
    if (got == 0) {
      close(fd);
      return false;
    }
    cursor += got;
    len -= static_cast<std::size_t>(got);
  }

  close(fd);
  return true;
}

std::uint32_t random_u32() {
  if (rng_offset + 4 > kBufferSize) {
    if (!rng_bytes(rng_buffer, sizeof rng_buffer)) {
      std::fputs("passgen: CSPRNG failure\n", stderr);
      std::exit(2);
    }
    rng_offset = 0;
  }

  const unsigned char *bytes = rng_buffer + rng_offset;
  rng_offset += 4;
  return static_cast<std::uint32_t>(bytes[0]) |
         (static_cast<std::uint32_t>(bytes[1]) << 8) |
         (static_cast<std::uint32_t>(bytes[2]) << 16) |
         (static_cast<std::uint32_t>(bytes[3]) << 24);
}

} // namespace

bool rng_bytes(void *buffer, std::size_t len) {
#if defined(__ANDROID__)
  arc4random_buf(buffer, len);
  return true;
#elif defined(__linux__)
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
    cursor += got;
    remaining -= static_cast<std::size_t>(got);
  }
  if (remaining == 0) {
    return true;
  }
#endif

  return read_urandom(buffer, len);
}

std::size_t rng_below(std::size_t n) {
  if (n <= 1) {
    return 0;
  }

  const std::uint64_t limit =
      ((static_cast<std::uint64_t>(1) << 32) / n) * n;
  for (;;) {
    std::uint32_t value = random_u32();
    if (static_cast<std::uint64_t>(value) < limit) {
      return static_cast<std::size_t>(value % n);
    }
  }
}
