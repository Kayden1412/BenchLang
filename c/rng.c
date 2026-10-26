#define _GNU_SOURCE
#include "rng.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#if defined(__ANDROID__)
#include <stdlib.h>
#elif defined(__linux__)
#include <sys/random.h>
#endif

/* ALT_RNG_REV_0 -- leaf file used by the incremental edit test. */

#define RNG_BUFFER_SIZE 4096

/*
 * All implementations read the system CSPRNG through the same 4096-byte
 * buffer and consume little-endian 32-bit words. This keeps the random-value
 * consumption pattern identical across languages; only the OS call used to
 * fill the buffer differs.
 */
static unsigned char rng_buffer[RNG_BUFFER_SIZE];
static size_t rng_offset = RNG_BUFFER_SIZE;

static int read_urandom(void *buffer, size_t len) {
  int fd = open("/dev/urandom", O_RDONLY);
  if (fd < 0) {
    return 0;
  }

  unsigned char *cursor = (unsigned char *)buffer;
  while (len > 0) {
    ssize_t got = read(fd, cursor, len);
    if (got < 0) {
      if (errno == EINTR) {
        continue;
      }
      close(fd);
      return 0;
    }
    if (got == 0) {
      close(fd);
      return 0;
    }
    cursor += got;
    len -= (size_t)got;
  }

  close(fd);
  return 1;
}

int rng_bytes(void *buffer, size_t len) {
#if defined(__ANDROID__)
  arc4random_buf(buffer, len);
  return 1;
#elif defined(__linux__)
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
    cursor += got;
    remaining -= (size_t)got;
  }
  if (remaining == 0) {
    return 1;
  }
#endif

  return read_urandom(buffer, len);
}

static uint32_t random_u32(void) {
  if (rng_offset + 4 > RNG_BUFFER_SIZE) {
    if (!rng_bytes(rng_buffer, sizeof rng_buffer)) {
      fputs("passgen: CSPRNG failure\n", stderr);
      exit(2);
    }
    rng_offset = 0;
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
    uint32_t value = random_u32();
    if ((uint64_t)value < limit) {
      return (size_t)(value % n);
    }
  }
}
