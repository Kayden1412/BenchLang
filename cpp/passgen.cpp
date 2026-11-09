#include "rng.hpp"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

constexpr std::size_t kMaxPool = 64;
constexpr std::size_t kMaxCombined = 256;
constexpr std::size_t kMaxClasses = 4;
constexpr std::size_t kMaxLength = 1024;
constexpr std::size_t kMaxCount = 100000;

const char *kLower = "abcdefghijklmnopqrstuvwxyz";
const char *kUpper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const char *kDigit = "0123456789";
const char *kSymbol = "!@#$%^&*()-_=+[]{};:,.?/";

const char *kClassNames[kMaxClasses] = {"lower", "upper", "digit", "symbol"};
const char *kClassSources[kMaxClasses] = {kLower, kUpper, kDigit, kSymbol};

const char *kUsage =
    "usage: passgen [options]\n"
    "\n"
    "  --length N          password length (default 16)\n"
    "  --count N           number of passwords (default 5)\n"
    "  --classes LIST      comma-separated subset of: lower,upper,digit,symbol\n"
    "  --no-ambiguous      remove l, I, 1, O, 0 from the pools\n"
    "  --format FORMAT     plain (default) or json\n"
    "  --help              print this help\n";

struct Pool {
  char chars[kMaxPool];
  std::size_t len;
};

[[noreturn]] void fail(const char *message) {
  std::fprintf(stderr, "passgen: %s\n", message);
  std::exit(2);
}

bool parse_u32(const char *text, std::uint32_t &out) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    return false;
  }

  char *end = nullptr;
  errno = 0;
  unsigned long value = std::strtoul(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' ||
      value > 0xFFFFFFFFul) {
    return false;
  }

  out = static_cast<std::uint32_t>(value);
  return true;
}

bool is_ambiguous(char c) {
  return c == 'l' || c == 'I' || c == '1' || c == 'O' || c == '0';
}

int class_index(const char *name, std::size_t len) {
  for (std::size_t i = 0; i < kMaxClasses; i++) {
    if (std::strlen(kClassNames[i]) == len &&
        std::strncmp(kClassNames[i], name, len) == 0) {
      return static_cast<int>(i);
    }
  }
  return -1;
}

void build_pools(const char *argument, bool no_ambiguous, Pool *pools,
                 std::size_t &pool_count, char *combined,
                 std::size_t &combined_len) {
  bool selected[kMaxClasses] = {false, false, false, false};
  const char *cursor = argument;

  if (argument == nullptr || *argument == '\0') {
    fail("no character classes selected");
  }

  for (;;) {
    const char *comma = std::strchr(cursor, ',');
    const char *end =
        (comma == nullptr) ? cursor + std::strlen(cursor) : comma;
    const char *start = cursor;

    while (start < end && (*start == ' ' || *start == '\t')) {
      start++;
    }
    while (end > start && (end[-1] == ' ' || end[-1] == '\t')) {
      end--;
    }

    std::size_t len = static_cast<std::size_t>(end - start);
    if (len > 0) {
      int index = class_index(start, len);
      if (index < 0) {
        fail("unknown character class");
      }
      selected[index] = true;
    }

    if (comma == nullptr) {
      break;
    }
    cursor = comma + 1;
  }

  pool_count = 0;
  combined_len = 0;

  for (std::size_t i = 0; i < kMaxClasses; i++) {
    if (!selected[i]) {
      continue;
    }

    const char *source = kClassSources[i];
    Pool &pool = pools[pool_count];
    std::size_t written = 0;

    for (const char *c = source; *c != '\0'; c++) {
      if (no_ambiguous && is_ambiguous(*c)) {
        continue;
      }
      if (written >= kMaxPool) {
        fail("character class list is too long");
      }
      pool.chars[written++] = *c;
    }
    if (written == 0) {
      fail("class is empty after --no-ambiguous");
    }
    pool.len = written;

    if (combined_len + written > kMaxCombined) {
      fail("character class list is too long");
    }
    std::memcpy(combined + combined_len, pool.chars, written);
    combined_len += written;
    pool_count++;
  }

  if (pool_count == 0) {
    fail("no character classes selected");
  }
}

void generate_password(std::size_t length, const Pool *pools,
                       std::size_t pool_count, const char *combined,
                       std::size_t combined_len, char *out) {
  std::size_t position = 0;

  for (std::size_t i = 0; i < pool_count; i++) {
    out[position++] = pools[i].chars[rng_below(pools[i].len)];
  }
  while (position < length) {
    out[position++] = combined[rng_below(combined_len)];
  }

  for (std::size_t i = length; i > 1; i--) {
    std::size_t j = rng_below(i);
    char tmp = out[i - 1];
    out[i - 1] = out[j];
    out[j] = tmp;
  }
  out[length] = '\0';
}

std::uint32_t fnv1a(std::uint32_t hash, const char *data, std::size_t len) {
  for (std::size_t i = 0; i < len; i++) {
    hash ^= static_cast<unsigned char>(data[i]);
    hash *= 16777619u;
  }
  return hash;
}

} // namespace

int main(int argc, char **argv) {
  static char output_buffer[4096];
  std::setvbuf(stdout, output_buffer, _IOFBF, sizeof output_buffer);

  std::size_t length = 16;
  std::size_t count = 5;
  const char *classes = "lower,upper,digit,symbol";
  bool no_ambiguous = false;
  bool as_json = false;

  for (int i = 1; i < argc; i++) {
    const char *arg = argv[i];

    if (std::strcmp(arg, "--help") == 0 || std::strcmp(arg, "-h") == 0) {
      std::fputs(kUsage, stdout);
      return 0;
    }

    if (std::strcmp(arg, "--no-ambiguous") == 0) {
      no_ambiguous = true;
      continue;
    }

    if (std::strcmp(arg, "--length") == 0 ||
        std::strcmp(arg, "--count") == 0 ||
        std::strcmp(arg, "--classes") == 0 ||
        std::strcmp(arg, "--format") == 0) {
      if (i + 1 >= argc) {
        fail("option needs a value");
      }
      const char *value = argv[++i];

      if (std::strcmp(arg, "--classes") == 0) {
        classes = value;
      } else if (std::strcmp(arg, "--format") == 0) {
        if (std::strcmp(value, "json") == 0) {
          as_json = true;
        } else if (std::strcmp(value, "plain") == 0) {
          as_json = false;
        } else {
          fail("--format must be plain or json");
        }
      } else if (std::strcmp(arg, "--length") == 0) {
        std::uint32_t parsed = 0;
        if (!parse_u32(value, parsed) || parsed < 1 || parsed > kMaxLength) {
          fail("--length must be between 1 and 1024");
        }
        length = parsed;
      } else {
        std::uint32_t parsed = 0;
        if (!parse_u32(value, parsed) || parsed < 1 || parsed > kMaxCount) {
          fail("--count must be between 1 and 100000");
        }
        count = parsed;
      }
      continue;
    }

    fail("unknown argument");
  }

  Pool pools[kMaxClasses];
  char combined[kMaxCombined];
  std::size_t pool_count = 0;
  std::size_t combined_len = 0;
  build_pools(classes, no_ambiguous, pools, pool_count, combined,
              combined_len);
  if (length < pool_count) {
    fail("--length is smaller than the number of selected classes");
  }

  char password[kMaxLength + 1];
  std::uint32_t checksum = 2166136261u;

  if (as_json) {
    std::fputs("{\"passwords\":[", stdout);
  }

  for (std::size_t i = 0; i < count; i++) {
    generate_password(length, pools, pool_count, combined, combined_len,
                      password);
    checksum = fnv1a(checksum, password, length);
    checksum = fnv1a(checksum, "\n", 1);

    if (as_json) {
      if (i > 0) {
        std::fputc(',', stdout);
      }
      std::printf("\"%s\"", password);
    } else {
      std::printf("%s\n", password);
    }
  }

  if (as_json) {
    std::printf("],\"checksum\":\"%08x\"}\n", checksum);
  } else {
    std::printf("checksum=%08x\n", checksum);
  }

  return 0;
}
