package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const maxLength = 1024
const maxCount = 100000
const maxPool = 64
const maxCombined = 256
const outputSize = 4096

const lower = "abcdefghijklmnopqrstuvwxyz"
const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
const digit = "0123456789"
const symbol = "!@#$%^&*()-_=+[]{};:,.?/"

const usage = `usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
`

var classNames = [4]string{"lower", "upper", "digit", "symbol"}
var classSources = [4]string{lower, upper, digit, symbol}
var newline = [1]byte{'\n'}

type pool struct {
	chars [maxPool]byte
	len   int
}

func fail(message string) {
	fmt.Fprintf(os.Stderr, "passgen: %s\n", message)
	os.Exit(2)
}

func parseInteger(value string, name string) uint64 {
	parsed, err := strconv.ParseUint(value, 10, 32)
	if err != nil {
		fail(name + " expects an integer")
	}
	return parsed
}

func isAmbiguous(ch byte) bool {
	return ch == 'l' || ch == 'I' || ch == '1' || ch == 'O' || ch == '0'
}

func classIndex(name string) int {
	for index, candidate := range classNames {
		if candidate == name {
			return index
		}
	}
	return -1
}

func buildPools(argument string, noAmbiguous bool, pools *[4]pool, combined *[maxCombined]byte) (int, int) {
	var selected [4]bool

	start := 0
	for start <= len(argument) {
		comma := strings.IndexByte(argument[start:], ',')
		end := len(argument)
		if comma >= 0 {
			end = start + comma
		}

		name := strings.TrimSpace(argument[start:end])
		if name != "" {
			index := classIndex(name)
			if index < 0 {
				fail("unknown character class")
			}
			selected[index] = true
		}

		if comma < 0 {
			break
		}
		start = end + 1
	}

	poolCount := 0
	combinedLen := 0

	for index, source := range classSources {
		if !selected[index] {
			continue
		}

		pool := &pools[poolCount]
		written := 0
		for i := 0; i < len(source); i++ {
			ch := source[i]
			if noAmbiguous && isAmbiguous(ch) {
				continue
			}
			pool.chars[written] = ch
			written++
		}
		if written == 0 {
			fail("class is empty after --no-ambiguous")
		}
		pool.len = written

		copy(combined[combinedLen:], pool.chars[:written])
		combinedLen += written
		poolCount++
	}

	if poolCount == 0 {
		fail("no character classes selected")
	}

	return poolCount, combinedLen
}

func generatePassword(length int, pools []pool, combined []byte, out []byte) {
	position := 0

	for i := range pools {
		out[position] = pools[i].chars[below(uint64(pools[i].len))]
		position++
	}
	for position < length {
		out[position] = combined[below(uint64(len(combined)))]
		position++
	}

	for i := length; i > 1; i-- {
		j := int(below(uint64(i)))
		out[i-1], out[j] = out[j], out[i-1]
	}
}

func fnv1a(hash uint32, data []byte) uint32 {
	for _, ch := range data {
		hash ^= uint32(ch)
		hash *= 16777619
	}
	return hash
}

func main() {
	length := 16
	count := 5
	classes := "lower,upper,digit,symbol"
	noAmbiguous := false
	asJSON := false

	args := os.Args[1:]
	for i := 0; i < len(args); i++ {
		arg := args[i]

		if arg == "--help" || arg == "-h" {
			os.Stdout.WriteString(usage)
			return
		}

		if arg == "--no-ambiguous" {
			noAmbiguous = true
			continue
		}

		if arg == "--length" || arg == "--count" || arg == "--classes" || arg == "--format" {
			if i+1 >= len(args) {
				fail("option needs a value")
			}
			i++
			value := args[i]

			switch arg {
			case "--classes":
				classes = value
			case "--format":
				switch value {
				case "json":
					asJSON = true
				case "plain":
					asJSON = false
				default:
					fail("--format must be plain or json")
				}
			case "--length":
				parsed := parseInteger(value, "--length")
				if parsed < 1 || parsed > maxLength {
					fail("--length must be between 1 and 1024")
				}
				length = int(parsed)
			default:
				parsed := parseInteger(value, "--count")
				if parsed < 1 || parsed > maxCount {
					fail("--count must be between 1 and 100000")
				}
				count = int(parsed)
			}
			continue
		}

		fail("unknown argument")
	}

	var pools [4]pool
	var combined [maxCombined]byte
	poolCount, combinedLen := buildPools(classes, noAmbiguous, &pools, &combined)
	if length < poolCount {
		fail("--length is smaller than the number of selected classes")
	}

	var password [maxLength]byte
	var checksum uint32 = 2166136261
	out := bufio.NewWriterSize(os.Stdout, outputSize)

	if asJSON {
		out.WriteString("{\"passwords\":[")
	}

	for index := 0; index < count; index++ {
		generatePassword(length, pools[:poolCount], combined[:combinedLen], password[:length])
		checksum = fnv1a(checksum, password[:length])
		checksum = fnv1a(checksum, newline[:])

		if asJSON {
			if index > 0 {
				out.WriteByte(',')
			}
			out.WriteByte('"')
			out.Write(password[:length])
			out.WriteByte('"')
		} else {
			out.Write(password[:length])
			out.WriteByte('\n')
		}
	}

	if asJSON {
		fmt.Fprintf(out, "],\"checksum\":\"%08x\"}\n", checksum)
	} else {
		fmt.Fprintf(out, "checksum=%08x\n", checksum)
	}

	out.Flush()
}
