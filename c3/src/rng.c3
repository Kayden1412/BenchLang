//! System CSPRNG wrapper.
//!
//! ALT_RNG_REV_0 -- leaf file used by the incremental edit test.
//!
//! `std::crypto::entropy` reads from the operating system's cryptographic
//! random source (getrandom on Linux). No seeded PRNG is used.
//!
//! All implementations read the system CSPRNG through the same 4096-byte
//! buffer and consume little-endian 32-bit words. This keeps the random-value
//! consumption pattern identical across languages; only the OS call used to
//! fill the buffer differs.

module passgen;

import std::io;
import std::os;
import std::crypto::entropy;

const BUFFER_SIZE = 4096;

char[BUFFER_SIZE] rng_buffer;
usz rng_offset = BUFFER_SIZE;

fn void fill(char[] buf)
{
	if (catch err = entropy::fill(buf))
	{
		io::eprintn("passgen: CSPRNG failure");
		os::exit(2);
	}
}

fn void refill()
{
	fill(rng_buffer[..]);
	rng_offset = 0;
}

fn uint next_u32()
{
	if (rng_offset + 4 > BUFFER_SIZE)
	{
		refill();
	}

	uint b0 = (uint)rng_buffer[rng_offset];
	uint b1 = (uint)rng_buffer[rng_offset + 1];
	uint b2 = (uint)rng_buffer[rng_offset + 2];
	uint b3 = (uint)rng_buffer[rng_offset + 3];
	rng_offset += 4;
	return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
}

/// Uniform integer in `[0, n)` with rejection sampling.
fn usz below(usz n)
{
	if (n <= 1) return 0;

	ulong limit = (((ulong)1 << 32) / n) * n;
	while (true)
	{
		ulong value = (ulong)next_u32();
		if (value < limit) return (usz)(value % n);
	}
}
