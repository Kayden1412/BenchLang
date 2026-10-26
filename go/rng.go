package main

// ALT_RNG_REV_0 -- leaf file used by the incremental edit test.
//
// crypto/rand reads from the operating system CSPRNG. There is no seeded PRNG
// and no math/rand usage anywhere in this program.
//
// All implementations read the system CSPRNG through the same 4096-byte
// buffer and consume little-endian 32-bit words. This keeps the random-value
// consumption pattern identical across languages; only the OS call used to
// fill the buffer differs.

import (
	"crypto/rand"
	"encoding/binary"
	"fmt"
	"os"
)

const bufferSize = 4096

var rngBuffer [bufferSize]byte
var rngOffset = bufferSize

// fill reads cryptographically secure bytes from the operating system.
func fill(buffer []byte) {
	if _, err := rand.Read(buffer); err != nil {
		fmt.Fprintln(os.Stderr, "passgen: CSPRNG failure")
		os.Exit(2)
	}
}

func nextU32() uint32 {
	if rngOffset+4 > bufferSize {
		fill(rngBuffer[:])
		rngOffset = 0
	}

	value := binary.LittleEndian.Uint32(rngBuffer[rngOffset : rngOffset+4])
	rngOffset += 4
	return value
}

// below returns a uniform integer in [0, n) using rejection sampling.
func below(n uint64) uint64 {
	if n <= 1 {
		return 0
	}

	limit := ((uint64(1) << 32) / n) * n
	for {
		value := uint64(nextU32())
		if value < limit {
			return value % n
		}
	}
}
