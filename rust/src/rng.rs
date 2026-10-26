//! System CSPRNG wrapper.
//!
//! ALT_RNG_REV_0 -- leaf file used by the incremental edit test.
//!
//! Uses `/dev/urandom`, which is available on Linux and the BSDs without an
//! external crate. On Windows a different source would be required.
//!
//! All implementations read the system CSPRNG through the same 4096-byte
//! buffer and consume little-endian 32-bit words. This keeps the random-value
//! consumption pattern identical across languages; only the OS call used to
//! fill the buffer differs.

use std::fs::File;
use std::io::Read;

const BUFFER_SIZE: usize = 4096;

pub struct Random {
    source: File,
    buffer: [u8; BUFFER_SIZE],
    offset: usize,
}

impl Random {
    pub fn new() -> std::io::Result<Self> {
        Ok(Self {
            source: File::open("/dev/urandom")?,
            buffer: [0u8; BUFFER_SIZE],
            offset: BUFFER_SIZE,
        })
    }

    fn refill(&mut self) {
        if self.source.read_exact(&mut self.buffer).is_err() {
            eprintln!("passgen: CSPRNG failure");
            std::process::exit(2);
        }
        self.offset = 0;
    }

    fn next_u32(&mut self) -> u32 {
        if self.offset + 4 > BUFFER_SIZE {
            self.refill();
        }

        let offset = self.offset;
        self.offset += 4;
        u32::from_le_bytes([
            self.buffer[offset],
            self.buffer[offset + 1],
            self.buffer[offset + 2],
            self.buffer[offset + 3],
        ])
    }

    /// Uniform integer in `[0, n)` with rejection sampling.
    pub fn below(&mut self, n: usize) -> usize {
        if n <= 1 {
            return 0;
        }

        let limit = ((1u64 << 32) / n as u64) * n as u64;
        loop {
            let value = self.next_u32() as u64;
            if value < limit {
                return (value % n as u64) as usize;
            }
        }
    }
}
