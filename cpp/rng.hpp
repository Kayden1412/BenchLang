#pragma once

#include <cstddef>

/* Uniform integer in [0, n) with rejection sampling; exits on CSPRNG failure. */
std::size_t rng_below(std::size_t n);
