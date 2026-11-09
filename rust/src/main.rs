mod rng;

use std::io::{BufWriter, Write};

use rng::Random;

const MAX_LENGTH: usize = 1024;
const MAX_COUNT: usize = 100000;
const MAX_POOL: usize = 64;
const MAX_COMBINED: usize = 256;

const LOWER: &str = "abcdefghijklmnopqrstuvwxyz";
const UPPER: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const DIGIT: &str = "0123456789";
const SYMBOL: &str = "!@#$%^&*()-_=+[]{};:,.?/";
const CLASS_NAMES: [&str; 4] = ["lower", "upper", "digit", "symbol"];
const CLASS_SOURCES: [&str; 4] = [LOWER, UPPER, DIGIT, SYMBOL];

const USAGE: &str = "usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
";

#[derive(Clone, Copy)]
struct Pool {
    chars: [u8; MAX_POOL],
    len: usize,
}

const EMPTY_POOL: Pool = Pool {
    chars: [0u8; MAX_POOL],
    len: 0,
};

fn fail(message: &str) -> ! {
    eprintln!("passgen: {message}");
    std::process::exit(2);
}

fn is_ambiguous(c: u8) -> bool {
    matches!(c, b'l' | b'I' | b'1' | b'O' | b'0')
}

fn build_pools(
    argument: &str,
    no_ambiguous: bool,
    pools: &mut [Pool; 4],
    combined: &mut [u8; MAX_COMBINED],
) -> (usize, usize) {
    let mut selected = [false; 4];

    for part in argument.split(',') {
        let name = part.trim();
        if name.is_empty() {
            continue;
        }
        let index = CLASS_NAMES
            .iter()
            .position(|candidate| *candidate == name)
            .unwrap_or_else(|| fail("unknown character class"));
        selected[index] = true;
    }

    let mut pool_count = 0;
    let mut combined_len = 0;

    for (index, source) in CLASS_SOURCES.iter().enumerate() {
        if !selected[index] {
            continue;
        }

        let mut written = 0;
        for &c in source.as_bytes() {
            if no_ambiguous && is_ambiguous(c) {
                continue;
            }
            pools[pool_count].chars[written] = c;
            written += 1;
        }
        if written == 0 {
            fail("class is empty after --no-ambiguous");
        }
        pools[pool_count].len = written;

        combined[combined_len..combined_len + written]
            .copy_from_slice(&pools[pool_count].chars[..written]);
        combined_len += written;
        pool_count += 1;
    }

    if pool_count == 0 {
        fail("no character classes selected");
    }

    (pool_count, combined_len)
}

fn generate_password(
    length: usize,
    pools: &[Pool],
    combined: &[u8],
    random: &mut Random,
    out: &mut [u8],
) {
    let mut position = 0;
    for pool in pools {
        out[position] = pool.chars[random.below(pool.len)];
        position += 1;
    }
    while position < length {
        out[position] = combined[random.below(combined.len())];
        position += 1;
    }

    for i in (1..length).rev() {
        let j = random.below(i + 1);
        out.swap(i, j);
    }
}

fn fnv1a(mut hash: u32, data: &[u8]) -> u32 {
    for &byte in data {
        hash ^= byte as u32;
        hash = hash.wrapping_mul(16777619);
    }
    hash
}

fn main() {
    let mut length = 16usize;
    let mut count = 5usize;
    let mut classes = String::from("lower,upper,digit,symbol");
    let mut no_ambiguous = false;
    let mut as_json = false;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        let arg = arg.as_str();

        if arg == "--help" || arg == "-h" {
            print!("{USAGE}");
            return;
        }

        if arg == "--no-ambiguous" {
            no_ambiguous = true;
            continue;
        }

        if arg == "--length" || arg == "--count" || arg == "--classes" || arg == "--format" {
            let value = args.next().unwrap_or_else(|| fail("option needs a value"));

            match arg {
                "--classes" => classes = value,
                "--format" => match value.as_str() {
                    "json" => as_json = true,
                    "plain" => as_json = false,
                    _ => fail("--format must be plain or json"),
                },
                "--length" => {
                    length = value
                        .parse::<usize>()
                        .unwrap_or_else(|_| fail("--length expects an integer"));
                    if !(1..=MAX_LENGTH).contains(&length) {
                        fail("--length must be between 1 and 1024");
                    }
                }
                _ => {
                    count = value
                        .parse::<usize>()
                        .unwrap_or_else(|_| fail("--count expects an integer"));
                    if !(1..=MAX_COUNT).contains(&count) {
                        fail("--count must be between 1 and 100000");
                    }
                }
            }
            continue;
        }

        fail("unknown argument");
    }

    let mut pools = [EMPTY_POOL; 4];
    let mut combined = [0u8; MAX_COMBINED];
    let (pool_count, combined_len) =
        build_pools(&classes, no_ambiguous, &mut pools, &mut combined);
    if length < pool_count {
        fail("--length is smaller than the number of selected classes");
    }

    let mut random = Random::new().unwrap_or_else(|_| fail("CSPRNG failure"));
    let mut password = [0u8; MAX_LENGTH];
    let mut checksum = 2166136261u32;
    let stdout = std::io::stdout();
    let mut writer = BufWriter::with_capacity(4096, stdout.lock());

    if as_json {
        writer
            .write_all(b"{\"passwords\":[")
            .expect("failed to write stdout");
    }

    for index in 0..count {
        generate_password(
            length,
            &pools[..pool_count],
            &combined[..combined_len],
            &mut random,
            &mut password[..length],
        );
        checksum = fnv1a(checksum, &password[..length]);
        checksum = fnv1a(checksum, b"\n");

        if as_json {
            if index > 0 {
                writer.write_all(b",").expect("failed to write stdout");
            }
            writer.write_all(b"\"").expect("failed to write stdout");
            writer
                .write_all(&password[..length])
                .expect("failed to write stdout");
            writer.write_all(b"\"").expect("failed to write stdout");
        } else {
            writer
                .write_all(&password[..length])
                .expect("failed to write stdout");
            writer.write_all(b"\n").expect("failed to write stdout");
        }
    }

    if as_json {
        write!(writer, "],\"checksum\":\"{checksum:08x}\"}}\n").expect("failed to write stdout");
    } else {
        write!(writer, "checksum={checksum:08x}\n").expect("failed to write stdout");
    }

    writer.flush().expect("failed to write stdout");
}
