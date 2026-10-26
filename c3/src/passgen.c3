module passgen;

import std::io;
import std::os;

const MAX_LENGTH = 1024;
const MAX_COUNT = 100000;

const LOWER = "abcdefghijklmnopqrstuvwxyz";
const UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const DIGIT = "0123456789";
const SYMBOL = "!@#$%^&*()-_=+[]{};:,.?/";

const String[4] CLASS_NAMES = { "lower", "upper", "digit", "symbol" };
const String[4] CLASS_SOURCES = { LOWER, UPPER, DIGIT, SYMBOL };

const USAGE = `usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
`;

struct Pool
{
	char[] chars;
}

fn void fail(String message)
{
	io::eprintf("passgen: %s\n", message);
	os::exit(2);
}

fn usz? class_index(String name)
{
	foreach (index, candidate : CLASS_NAMES)
	{
		if (name == candidate) return (usz)index;
	}
	return NOT_FOUND~;
}

fn bool is_ambiguous(char c)
{
	return c == 'l' || c == 'I' || c == '1' || c == 'O' || c == '0';
}

fn char[] build_pool(String source, bool no_ambiguous, char[] buffer)
{
	usz len = 0;
	foreach (c : source)
	{
		if (no_ambiguous && is_ambiguous(c)) continue;
		buffer[len] = c;
		len++;
	}
	return buffer[0:len];
}

fn void generate(usz length, Pool[] pools, char[] combined, char[] out)
{
	usz position = 0;
	foreach (pool : pools)
	{
		out[position] = pool.chars[below(pool.chars.len)];
		position++;
	}
	while (position < length)
	{
		out[position] = combined[below(combined.len)];
		position++;
	}
	for (usz i = length; i > 1; i--)
	{
		usz j = below(i);
		char tmp = out[i - 1];
		out[i - 1] = out[j];
		out[j] = tmp;
	}
}

fn uint fnv1a(uint hash, char[] data)
{
	foreach (byte : data)
	{
		hash ^= (uint)byte;
		hash *= 16777619;
	}
	return hash;
}

fn int main(int argc, char** argv)
{
	usz length = 16;
	usz count = 5;
	String classes = "lower,upper,digit,symbol";
	bool no_ambiguous = false;
	bool as_json = false;

	for (int i = 1; i < argc; i++)
	{
		String arg = ((ZString)argv[i]).str_view();

		if (arg == "--help" || arg == "-h")
		{
			io::print(USAGE);
			return 0;
		}
		if (arg == "--no-ambiguous")
		{
			no_ambiguous = true;
			continue;
		}
		if (arg == "--length")
		{
			if (i + 1 >= argc) fail("--length requires a value");
			i++;
			String value = ((ZString)argv[i]).str_view();
			if (try int parsed = value.to_int())
			{
				if (parsed < 1 || parsed > MAX_LENGTH) fail("--length must be between 1 and 1024");
				length = (usz)parsed;
			}
			else
			{
				fail("--length expects an integer");
			}
			continue;
		}
		if (arg == "--count")
		{
			if (i + 1 >= argc) fail("--count requires a value");
			i++;
			String value = ((ZString)argv[i]).str_view();
			if (try int parsed = value.to_int())
			{
				if (parsed < 1 || parsed > MAX_COUNT) fail("--count must be between 1 and 100000");
				count = (usz)parsed;
			}
			else
			{
				fail("--count expects an integer");
			}
			continue;
		}
		if (arg == "--classes")
		{
			if (i + 1 >= argc) fail("--classes requires a value");
			i++;
			classes = ((ZString)argv[i]).str_view();
			continue;
		}
		if (arg == "--format")
		{
			if (i + 1 >= argc) fail("--format requires a value");
			i++;
			String value = ((ZString)argv[i]).str_view();
			if (value == "plain")
			{
				as_json = false;
			}
			else if (value == "json")
			{
				as_json = true;
			}
			else
			{
				fail("--format must be plain or json");
			}
			continue;
		}
		fail("unknown argument");
	}

	bool[4] selected = { false, false, false, false };
	foreach (part : classes.tsplit(","))
	{
		String name = part.trim();
		if (!name.len) continue;
		if (try usz index = class_index(name))
		{
			selected[index] = true;
		}
		else
		{
			fail("unknown character class");
		}
	}

	char[256] pool_buffers;
	char[256] combined_buffer;
	usz combined_len = 0;
	Pool[4] pools;
	usz pool_count = 0;

	foreach (index, source : CLASS_SOURCES)
	{
		if (!selected[index]) continue;
		char[] buffer = pool_buffers[index * 64:64];
		char[] chars = build_pool(source, no_ambiguous, buffer);
		if (!chars.len) fail("class is empty after --no-ambiguous");
		pools[pool_count].chars = chars;
		pool_count++;
		foreach (c : chars)
		{
			combined_buffer[combined_len] = c;
			combined_len++;
		}
	}

	if (pool_count == 0) fail("no character classes selected");
	if (length < pool_count) fail("--length is smaller than the number of selected classes");

	Pool[] active_pools = pools[0:pool_count];
	char[] combined = combined_buffer[0:combined_len];

	char[MAX_LENGTH] password;
	uint checksum = 2166136261;

	if (as_json) io::print("{\"passwords\":[");

	usz index = 0;
	while (index < count)
	{
		char[] generated = password[0:length];
		generate(length, active_pools, combined, generated);
		checksum = fnv1a(checksum, generated);
		checksum = fnv1a(checksum, "\n");

		if (as_json)
		{
			if (index > 0) io::print(",");
			io::printf("\"%s\"", (String)generated);
		}
		else
		{
			io::printn((String)generated);
		}
		index++;
	}

	if (as_json)
	{
		io::printfn("],\"checksum\":\"%08x\"}", checksum);
	}
	else
	{
		io::printfn("checksum=%08x", checksum);
	}
	return 0;
}
