#ifndef PASSGEN_RNG_H
#define PASSGEN_RNG_H

#include <stddef.h>

/* Uniform integer in [0, n) with rejection sampling; exits on CSPRNG failure. */
size_t rng_below(size_t n);

#endif
