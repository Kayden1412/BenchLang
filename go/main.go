package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const maxLength = 1024
const maxCount = 100000

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

func isAmbiguous(ch rune) bool {
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

func buildPools(argument string, noAmbiguous bool) []string {
	var selected [4]bool

	for _, part := range strings.Split(argument, ",") {
		name := strings.TrimSpace(part)
		if name == "" {
			continue
		}
		index := classIndex(name)
		if index < 0 {
			fail("unknown class: " + name)
		}
		selected[index] = true
	}

	pools := make([]string, 0, len(classNames))
	for index, name := range classNames {
		if !selected[index] {
			continue
		}
		var builder strings.Builder
		for _, ch := range classSources[index] {
			if noAmbiguous && isAmbiguous(ch) {
				continue
			}
			builder.WriteRune(ch)
		}
		chars := builder.String()
		if chars == "" {
			fail("class " + name + " is empty after --no-ambiguous")
		}
		pools = append(pools, chars)
	}

	if len(pools) == 0 {
		fail("no character classes selected")
	}
	return pools
}

func generatePassword(length int, pools []string) string {
	combined := strings.Join(pools, "")
	out := make([]byte, length)
	position := 0

	for _, pool := range pools {
		out[position] = pool[below(uint64(len(pool)))]
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
	return string(out)
}

func fnv1a(hash uint32, text string) uint32 {
	for _, ch := range []byte(text) {
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
			fmt.Print(usage)
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

		fail("unknown argument: " + arg)
	}

	pools := buildPools(classes, noAmbiguous)
	if length < len(pools) {
		fail("--length is smaller than the number of selected classes")
	}

	passwords := make([]string, 0, count)
	var checksum uint32 = 2166136261
	for i := 0; i < count; i++ {
		password := generatePassword(length, pools)
		passwords = append(passwords, password)
		checksum = fnv1a(checksum, password)
		checksum = fnv1a(checksum, "\n")
	}

	writer := bufio.NewWriter(os.Stdout)
	defer writer.Flush()

	if asJSON {
		payload := struct {
			Passwords []string `json:"passwords"`
			Checksum  string   `json:"checksum"`
		}{
			Passwords: passwords,
			Checksum:  fmt.Sprintf("%08x", checksum),
		}
		encoded, err := json.Marshal(payload)
		if err != nil {
			fail("JSON encoding failed")
		}
		writer.Write(encoded)
		writer.WriteByte('\n')
		return
	}

	for _, password := range passwords {
		writer.WriteString(password)
		writer.WriteByte('\n')
	}
	fmt.Fprintf(writer, "checksum=%08x\n", checksum)
}
