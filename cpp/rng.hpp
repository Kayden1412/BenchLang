#pragma once

#include <cstddef>
#include <cstdint>

/* Fills buffer from the operating system CSPRNG. Returns true on success. */
bool rng_bytes(void *buffer, std::size_t len);

/* Uniform integer in [0, n) with rejection sampling; exits on CSPRNG failure. */
std::size_t rng_below(std::size_t n);
