#ifndef PASSGEN_RNG_H
#define PASSGEN_RNG_H

#include <stddef.h>
#include <stdint.h>

/* Fills buffer from the operating system CSPRNG. Returns 1 on success. */
int rng_bytes(void *buffer, size_t len);

/* Uniform integer in [0, n) with rejection sampling; exits on CSPRNG failure. */
size_t rng_below(size_t n);

#endif
