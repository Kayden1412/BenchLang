#!/usr/bin/env node
'use strict';

const { below } = require('./rng.js');

const MAX_LENGTH = 1024;
const MAX_COUNT = 100000;

const LOWER = 'abcdefghijklmnopqrstuvwxyz';
const UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const DIGIT = '0123456789';
const SYMBOL = '!@#$%^&*()-_=+[]{};:,.?/';
const CLASS_ORDER = ['lower', 'upper', 'digit', 'symbol'];
const SOURCES = { lower: LOWER, upper: UPPER, digit: DIGIT, symbol: SYMBOL };

const USAGE = `usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
`;

function fail(message) {
  process.stderr.write(`passgen: ${message}\n`);
  process.exit(2);
}

function parseInteger(value, name) {
  if (!/^[0-9]+$/.test(value)) {
    fail(`${name} expects an integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) {
    fail(`${name} is out of range`);
  }
  return parsed;
}

function isAmbiguous(ch) {
  return ch === 'l' || ch === 'I' || ch === '1' || ch === 'O' || ch === '0';
}

function buildPools(argument, noAmbiguous) {
  const selected = new Set();
  for (const part of argument.split(',')) {
    const name = part.trim();
    if (name.length === 0) {
      continue;
    }
    if (!Object.prototype.hasOwnProperty.call(SOURCES, name)) {
      fail(`unknown class: ${name}`);
    }
    selected.add(name);
  }

  const pools = [];
  for (const name of CLASS_ORDER) {
    if (!selected.has(name)) {
      continue;
    }
    let chars = SOURCES[name];
    if (noAmbiguous) {
      chars = [...chars].filter((ch) => !isAmbiguous(ch)).join('');
    }
    if (chars.length === 0) {
      fail(`class ${name} is empty after --no-ambiguous`);
    }
    pools.push(chars);
  }

  if (pools.length === 0) {
    fail('no character classes selected');
  }
  return pools;
}

function generatePassword(length, pools) {
  const combined = pools.join('');
  const chars = pools.map((pool) => pool[below(pool.length)]);
  while (chars.length < length) {
    chars.push(combined[below(combined.length)]);
  }
  for (let i = length - 1; i > 0; i--) {
    const j = below(i + 1);
    const tmp = chars[i];
    chars[i] = chars[j];
    chars[j] = tmp;
  }
  return chars.join('');
}

function fnv1a(hash, text) {
  let h = hash;
  for (const byte of Buffer.from(text, 'utf8')) {
    h ^= byte;
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

function main(argv) {
  let length = 16;
  let count = 5;
  let classes = 'lower,upper,digit,symbol';
  let noAmbiguous = false;
  let asJson = false;

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];

    if (arg === '--help' || arg === '-h') {
      process.stdout.write(USAGE);
      return 0;
    }

    if (arg === '--no-ambiguous') {
      noAmbiguous = true;
      continue;
    }

    if (arg === '--length' || arg === '--count' || arg === '--classes' || arg === '--format') {
      if (i + 1 >= argv.length) {
        fail('option needs a value');
      }
      const value = argv[++i];

      if (arg === '--classes') {
        classes = value;
      } else if (arg === '--format') {
        if (value === 'json') {
          asJson = true;
        } else if (value === 'plain') {
          asJson = false;
        } else {
          fail('--format must be plain or json');
        }
      } else if (arg === '--length') {
        length = parseInteger(value, '--length');
        if (length < 1 || length > MAX_LENGTH) {
          fail('--length must be between 1 and 1024');
        }
      } else {
        count = parseInteger(value, '--count');
        if (count < 1 || count > MAX_COUNT) {
          fail('--count must be between 1 and 100000');
        }
      }
      continue;
    }

    fail(`unknown argument: ${arg}`);
  }

  const pools = buildPools(classes, noAmbiguous);
  if (length < pools.length) {
    fail('--length is smaller than the number of selected classes');
  }

  let checksum = 2166136261;
  const passwords = [];

  for (let i = 0; i < count; i++) {
    const password = generatePassword(length, pools);
    passwords.push(password);
    checksum = fnv1a(checksum, password);
    checksum = fnv1a(checksum, '\n');
  }

  const hex = checksum.toString(16).padStart(8, '0');

  if (asJson) {
    process.stdout.write(
      `${JSON.stringify({ passwords, checksum: hex })}\n`,
    );
  } else {
    process.stdout.write(`${passwords.join('\n')}\nchecksum=${hex}\n`);
  }
  return 0;
}

process.exitCode = main(process.argv.slice(2));
