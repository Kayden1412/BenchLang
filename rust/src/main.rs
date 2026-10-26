mod rng;

use rng::Random;

const MAX_LENGTH: usize = 1024;
const MAX_COUNT: usize = 100000;

const LOWER: &str = "abcdefghijklmnopqrstuvwxyz";
const UPPER: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const DIGIT: &str = "0123456789";
const SYMBOL: &str = "!@#$%^&*()-_=+[]{};:,.?/";
const CLASS_ORDER: [&str; 4] = ["lower", "upper", "digit", "symbol"];

const USAGE: &str = "usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
";

fn fail(message: &str) -> ! {
    eprintln!("passgen: {message}");
    std::process::exit(2);
}

fn class_source(name: &str) -> Option<&'static str> {
    match name {
        "lower" => Some(LOWER),
        "upper" => Some(UPPER),
        "digit" => Some(DIGIT),
        "symbol" => Some(SYMBOL),
        _ => None,
    }
}

fn is_ambiguous(c: char) -> bool {
    matches!(c, 'l' | 'I' | '1' | 'O' | '0')
}

fn build_pools(argument: &str, no_ambiguous: bool) -> Vec<String> {
    let mut selected = [false; 4];

    for part in argument.split(',') {
        let name = part.trim();
        if name.is_empty() {
            continue;
        }
        let index = CLASS_ORDER
            .iter()
            .position(|candidate| *candidate == name)
            .unwrap_or_else(|| fail(&format!("unknown class: {name}")));
        selected[index] = true;
    }

    let mut pools = Vec::new();
    for (index, name) in CLASS_ORDER.iter().enumerate() {
        if !selected[index] {
            continue;
        }
        let source = class_source(name).unwrap();
        let chars: String = source
            .chars()
            .filter(|c| !no_ambiguous || !is_ambiguous(*c))
            .collect();
        if chars.is_empty() {
            fail(&format!("class {name} is empty after --no-ambiguous"));
        }
        pools.push(chars);
    }

    if pools.is_empty() {
        fail("no character classes selected");
    }
    pools
}

fn generate_password(length: usize, pools: &[String], random: &mut Random) -> String {
    let combined: String = pools.concat();
    let mut chars: Vec<char> = pools
        .iter()
        .map(|pool| {
            let bytes = pool.as_bytes();
            bytes[random.below(bytes.len())] as char
        })
        .collect();

    while chars.len() < length {
        let bytes = combined.as_bytes();
        chars.push(bytes[random.below(bytes.len())] as char);
    }

    for i in (1..length).rev() {
        let j = random.below(i + 1);
        chars.swap(i, j);
    }

    chars.into_iter().collect()
}

fn fnv1a(mut hash: u32, text: &str) -> u32 {
    for byte in text.as_bytes() {
        hash ^= *byte as u32;
        hash = hash.wrapping_mul(16777619);
    }
    hash
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut length = 16usize;
    let mut count = 5usize;
    let mut classes = String::from("lower,upper,digit,symbol");
    let mut no_ambiguous = false;
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        let arg = args[i].as_str();

        if arg == "--help" || arg == "-h" {
            print!("{USAGE}");
            return;
        }

        if arg == "--no-ambiguous" {
            no_ambiguous = true;
            i += 1;
            continue;
        }

        if arg == "--length" || arg == "--count" || arg == "--classes" || arg == "--format" {
            if i + 1 >= args.len() {
                fail("option needs a value");
            }
            let value = args[i + 1].as_str();
            i += 2;

            match arg {
                "--classes" => classes = value.to_string(),
                "--format" => match value {
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

        fail(&format!("unknown argument: {arg}"));
    }

    let pools = build_pools(&classes, no_ambiguous);
    if length < pools.len() {
        fail("--length is smaller than the number of selected classes");
    }

    let mut random =
        Random::new().unwrap_or_else(|error| fail(&format!("CSPRNG: {error}")));

    let mut checksum = 2166136261u32;

    if as_json {
        print!("{{\"passwords\":[");
    }

    for index in 0..count {
        let password = generate_password(length, &pools, &mut random);
        checksum = fnv1a(checksum, &password);
        checksum = fnv1a(checksum, "\n");

        if as_json {
            if index > 0 {
                print!(",");
            }
            print!("\"{password}\"");
        } else {
            println!("{password}");
        }
    }

    if as_json {
        println!("],\"checksum\":\"{checksum:08x}\"}}");
    } else {
        println!("checksum={checksum:08x}");
    }
}
