#include "rng.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_POOL 64
#define MAX_COMBINED 256
#define MAX_CLASSES 4
#define MAX_LENGTH 1024
#define MAX_COUNT 100000

typedef struct {
  char chars[MAX_POOL];
  size_t len;
} Pool;

static const char LOWER[] = "abcdefghijklmnopqrstuvwxyz";
static const char UPPER[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
static const char DIGIT[] = "0123456789";
static const char SYMBOL[] = "!@#$%^&*()-_=+[]{};:,.?/";

static const char *CLASS_NAMES[MAX_CLASSES] = {"lower", "upper", "digit",
                                               "symbol"};
static const char *CLASS_SOURCES[MAX_CLASSES] = {LOWER, UPPER, DIGIT, SYMBOL};

static const char *USAGE =
    "usage: passgen [options]\n"
    "\n"
    "  --length N          password length (default 16)\n"
    "  --count N           number of passwords (default 5)\n"
    "  --classes LIST      comma-separated subset of: lower,upper,digit,symbol\n"
    "  --no-ambiguous      remove l, I, 1, O, 0 from the pools\n"
    "  --format FORMAT     plain (default) or json\n"
    "  --help              print this help\n";

static void fail(const char *message) {
  fprintf(stderr, "passgen: %s\n", message);
  exit(2);
}

static int parse_u32(const char *text, uint32_t *out) {
  char *end = NULL;
  unsigned long value;

  if (text == NULL || *text == '\0' || *text == '-') {
    return 0;
  }

  errno = 0;
  value = strtoul(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || value > 0xFFFFFFFFul) {
    return 0;
  }

  *out = (uint32_t)value;
  return 1;
}

static int is_ambiguous(char c) {
  return c == 'l' || c == 'I' || c == '1' || c == 'O' || c == '0';
}

static int class_index(const char *name, size_t len) {
  for (int i = 0; i < MAX_CLASSES; i++) {
    if (strlen(CLASS_NAMES[i]) == len &&
        strncmp(CLASS_NAMES[i], name, len) == 0) {
      return i;
    }
  }
  return -1;
}

static void build_pools(const char *argument, int no_ambiguous, Pool *pools,
                        size_t *pool_count, char *combined,
                        size_t *combined_len) {
  int selected[MAX_CLASSES] = {0, 0, 0, 0};
  const char *cursor = argument;

  if (argument == NULL || *argument == '\0') {
    fail("no character classes selected");
  }

  for (;;) {
    const char *comma = strchr(cursor, ',');
    const char *end = (comma == NULL) ? cursor + strlen(cursor) : comma;
    const char *start = cursor;

    while (start < end && (*start == ' ' || *start == '\t')) {
      start++;
    }
    while (end > start && (end[-1] == ' ' || end[-1] == '\t')) {
      end--;
    }

    size_t len = (size_t)(end - start);
    if (len > 0) {
      int index = class_index(start, len);
      if (index < 0) {
        fail("unknown character class");
      }
      selected[index] = 1;
    }

    if (comma == NULL) {
      break;
    }
    cursor = comma + 1;
  }

  *pool_count = 0;
  *combined_len = 0;

  for (int i = 0; i < MAX_CLASSES; i++) {
    if (!selected[i]) {
      continue;
    }

    const char *source = CLASS_SOURCES[i];
    Pool *pool = &pools[*pool_count];
    size_t written = 0;

    for (size_t j = 0; source[j] != '\0'; j++) {
      char c = source[j];
      if (no_ambiguous && is_ambiguous(c)) {
        continue;
      }
      if (written >= MAX_POOL) {
        fail("character class list is too long");
      }
      pool->chars[written++] = c;
    }
    if (written == 0) {
      fail("class is empty after --no-ambiguous");
    }
    pool->len = written;

    if (*combined_len + written > MAX_COMBINED) {
      fail("character class list is too long");
    }
    memcpy(combined + *combined_len, pool->chars, written);
    *combined_len += written;
    (*pool_count)++;
  }

  if (*pool_count == 0) {
    fail("no character classes selected");
  }
}

static void generate_password(size_t length, const Pool *pools,
                              size_t pool_count, const char *combined,
                              size_t combined_len, char *out) {
  size_t position = 0;

  for (size_t i = 0; i < pool_count; i++) {
    out[position++] = pools[i].chars[rng_below(pools[i].len)];
  }
  while (position < length) {
    out[position++] = combined[rng_below(combined_len)];
  }

  for (size_t i = length; i > 1; i--) {
    size_t j = rng_below(i);
    char tmp = out[i - 1];
    out[i - 1] = out[j];
    out[j] = tmp;
  }
  out[length] = '\0';
}

static uint32_t fnv1a(uint32_t hash, const char *data, size_t len) {
  for (size_t i = 0; i < len; i++) {
    hash ^= (unsigned char)data[i];
    hash *= 16777619u;
  }
  return hash;
}

int main(int argc, char **argv) {
  static char output_buffer[4096];
  setvbuf(stdout, output_buffer, _IOFBF, sizeof output_buffer);

  size_t length = 16;
  size_t count = 5;
  const char *classes = "lower,upper,digit,symbol";
  int no_ambiguous = 0;
  int as_json = 0;

  for (int i = 1; i < argc; i++) {
    const char *arg = argv[i];

    if (strcmp(arg, "--help") == 0 || strcmp(arg, "-h") == 0) {
      fputs(USAGE, stdout);
      return 0;
    }

    if (strcmp(arg, "--no-ambiguous") == 0) {
      no_ambiguous = 1;
      continue;
    }

    if (strcmp(arg, "--length") == 0 || strcmp(arg, "--count") == 0 ||
        strcmp(arg, "--classes") == 0 || strcmp(arg, "--format") == 0) {
      if (i + 1 >= argc) {
        fail("option needs a value");
      }
      const char *value = argv[++i];

      if (strcmp(arg, "--classes") == 0) {
        classes = value;
      } else if (strcmp(arg, "--format") == 0) {
        if (strcmp(value, "json") == 0) {
          as_json = 1;
        } else if (strcmp(value, "plain") == 0) {
          as_json = 0;
        } else {
          fail("--format must be plain or json");
        }
      } else if (strcmp(arg, "--length") == 0) {
        uint32_t parsed;
        if (!parse_u32(value, &parsed) || parsed < 1 || parsed > MAX_LENGTH) {
          fail("--length must be between 1 and 1024");
        }
        length = parsed;
      } else {
        uint32_t parsed;
        if (!parse_u32(value, &parsed) || parsed < 1 || parsed > MAX_COUNT) {
          fail("--count must be between 1 and 100000");
        }
        count = parsed;
      }
      continue;
    }

    fail("unknown argument");
  }

  Pool pools[MAX_CLASSES];
  char combined[MAX_COMBINED];
  size_t pool_count = 0;
  size_t combined_len = 0;
  build_pools(classes, no_ambiguous, pools, &pool_count, combined,
              &combined_len);
  if (length < pool_count) {
    fail("--length is smaller than the number of selected classes");
  }

  char password[MAX_LENGTH + 1];
  uint32_t checksum = 2166136261u;

  if (as_json) {
    fputs("{\"passwords\":[", stdout);
  }

  for (size_t i = 0; i < count; i++) {
    generate_password(length, pools, pool_count, combined, combined_len,
                      password);
    checksum = fnv1a(checksum, password, length);
    checksum = fnv1a(checksum, "\n", 1);

    if (as_json) {
      if (i > 0) {
        fputc(',', stdout);
      }
      printf("\"%s\"", password);
    } else {
      printf("%s\n", password);
    }
  }

  if (as_json) {
    printf("],\"checksum\":\"%08x\"}\n", checksum);
  } else {
    printf("checksum=%08x\n", checksum);
  }

  return 0;
}
