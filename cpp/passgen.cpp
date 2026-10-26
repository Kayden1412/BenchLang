#include "rng.hpp"

#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t kMaxLength = 1024;
constexpr std::size_t kMaxCount = 100000;
constexpr char kAmbiguous[] = "lI1O0";

const char *kLower = "abcdefghijklmnopqrstuvwxyz";
const char *kUpper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const char *kDigit = "0123456789";
const char *kSymbol = "!@#$%^&*()-_=+[]{};:,.?/";

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
  std::string name;
  std::string chars;
};

[[noreturn]] void fail(const std::string &message) {
  std::cerr << "passgen: " << message << '\n';
  std::exit(2);
}

bool parse_u32(const std::string &text, std::uint32_t &out) {
  if (text.empty() || text[0] == '-') {
    return false;
  }

  char *end = nullptr;
  errno = 0;
  unsigned long value = std::strtoul(text.c_str(), &end, 10);
  if (errno != 0 || end == text.c_str() || *end != '\0' ||
      value > 0xFFFFFFFFul) {
    return false;
  }

  out = static_cast<std::uint32_t>(value);
  return true;
}

bool is_ambiguous(char c) {
  return std::strchr(kAmbiguous, c) != nullptr;
}

const char *class_source(const std::string &name) {
  if (name == "lower") {
    return kLower;
  }
  if (name == "upper") {
    return kUpper;
  }
  if (name == "digit") {
    return kDigit;
  }
  if (name == "symbol") {
    return kSymbol;
  }
  return nullptr;
}

std::vector<Pool> build_pools(const std::string &argument, bool no_ambiguous) {
  bool selected[4] = {false, false, false, false};
  std::size_t start = 0;

  while (start <= argument.size()) {
    std::size_t comma = argument.find(',', start);
    std::size_t end = (comma == std::string::npos) ? argument.size() : comma;
    std::size_t first = start;
    std::size_t last = end;

    while (first < last && (argument[first] == ' ' || argument[first] == '\t')) {
      first++;
    }
    while (last > first &&
           (argument[last - 1] == ' ' || argument[last - 1] == '\t')) {
      last--;
    }

    std::string name = argument.substr(first, last - first);
    if (name.empty()) {
      if (comma == std::string::npos) {
        break;
      }
      start = comma + 1;
      continue;
    }

    int index = -1;
    if (name == "lower") {
      index = 0;
    } else if (name == "upper") {
      index = 1;
    } else if (name == "digit") {
      index = 2;
    } else if (name == "symbol") {
      index = 3;
    }

    if (index < 0) {
      fail("invalid character class list");
    }
    selected[index] = true;

    if (comma == std::string::npos) {
      break;
    }
    start = comma + 1;
  }

  std::vector<Pool> pools;
  for (int i = 0; i < 4; i++) {
    if (!selected[i]) {
      continue;
    }

    const char *name = (i == 0) ? "lower" : (i == 1) ? "upper" : (i == 2) ? "digit" : "symbol";
    const char *source = class_source(name);
    std::string chars;
    for (const char *cursor = source; *cursor != '\0'; cursor++) {
      if (no_ambiguous && is_ambiguous(*cursor)) {
        continue;
      }
      chars.push_back(*cursor);
    }
    if (chars.empty()) {
      fail("class is empty after --no-ambiguous");
    }
    pools.push_back({name, chars});
  }

  if (pools.empty()) {
    fail("no character classes selected");
  }
  return pools;
}

std::string generate_password(std::size_t length, const std::vector<Pool> &pools) {
  std::string combined;
  for (const Pool &pool : pools) {
    combined += pool.chars;
  }

  std::string out;
  out.reserve(length);
  for (const Pool &pool : pools) {
    out.push_back(pool.chars[rng_below(pool.chars.size())]);
  }
  while (out.size() < length) {
    out.push_back(combined[rng_below(combined.size())]);
  }

  for (std::size_t i = length; i > 1; i--) {
    std::size_t j = rng_below(i);
    std::swap(out[i - 1], out[j]);
  }
  return out;
}

std::uint32_t fnv1a(std::uint32_t hash, const std::string &text) {
  for (unsigned char byte : text) {
    hash ^= byte;
    hash *= 16777619u;
  }
  return hash;
}

} // namespace

int main(int argc, char **argv) {
  std::size_t length = 16;
  std::size_t count = 5;
  std::string classes = "lower,upper,digit,symbol";
  bool no_ambiguous = false;
  bool as_json = false;

  for (int i = 1; i < argc; i++) {
    std::string arg = argv[i];

    if (arg == "--help" || arg == "-h") {
      std::cout << kUsage;
      return 0;
    }

    if (arg == "--no-ambiguous") {
      no_ambiguous = true;
      continue;
    }

    if (arg == "--length" || arg == "--count" || arg == "--classes" ||
        arg == "--format") {
      if (i + 1 >= argc) {
        fail("option needs a value");
      }
      std::string value = argv[++i];

      if (arg == "--classes") {
        classes = value;
      } else if (arg == "--format") {
        if (value == "json") {
          as_json = true;
        } else if (value == "plain") {
          as_json = false;
        } else {
          fail("--format must be plain or json");
        }
      } else if (arg == "--length") {
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

  std::vector<Pool> pools = build_pools(classes, no_ambiguous);
  if (length < pools.size()) {
    fail("--length is smaller than the number of selected classes");
  }

  std::uint32_t checksum = 2166136261u;
  std::vector<std::string> passwords;
  passwords.reserve(count);

  if (as_json) {
    std::cout << "{\"passwords\":[";
  }

  for (std::size_t i = 0; i < count; i++) {
    std::string password = generate_password(length, pools);
    checksum = fnv1a(checksum, password);
    checksum = fnv1a(checksum, "\n");

    if (as_json) {
      if (i > 0) {
        std::cout << ',';
      }
      std::cout << '"' << password << '"';
    } else {
      std::cout << password << '\n';
    }
  }

  if (as_json) {
    std::cout << "],\"checksum\":\"" << std::hex << std::setw(8)
              << std::setfill('0') << checksum << "\"}\n";
  } else {
    std::cout << "checksum=" << std::hex << std::setw(8)
              << std::setfill('0') << checksum << '\n';
  }

  return 0;
}
