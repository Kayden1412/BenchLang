#!/usr/bin/env node
'use strict';

const { below } = require('./rng.js');

const MAX_LENGTH = 1024;
const MAX_COUNT = 100000;
const OUTPUT_SIZE = 4096;

const LOWER = 'abcdefghijklmnopqrstuvwxyz';
const UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const DIGIT = '0123456789';
const SYMBOL = '!@#$%^&*()-_=+[]{};:,.?/';
const CLASS_ORDER = ['lower', 'upper', 'digit', 'symbol'];
const SOURCES = { lower: LOWER, upper: UPPER, digit: DIGIT, symbol: SYMBOL };
const NEWLINE = Buffer.from('\n');

const USAGE = `usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
`;

class Output {
  constructor() {
    this.buf = Buffer.allocUnsafe(OUTPUT_SIZE);
    this.n = 0;
  }

  flush() {
    if (this.n > 0) {
      process.stdout.write(this.buf.subarray(0, this.n));
      this.n = 0;
    }
  }

  writeBuffer(buffer, start, end) {
    const size = end - start;
    if (size >= OUTPUT_SIZE) {
      this.flush();
      process.stdout.write(buffer.subarray(start, end));
      return;
    }
    if (this.n + size > OUTPUT_SIZE) {
      this.flush();
    }
    buffer.copy(this.buf, this.n, start, end);
    this.n += size;
  }

  writeByte(byte) {
    if (this.n === OUTPUT_SIZE) {
      this.flush();
    }
    this.buf[this.n++] = byte;
  }

  writeString(text) {
    for (let i = 0; i < text.length; i++) {
      this.writeByte(text.charCodeAt(i));
    }
  }

  writeHex(value) {
    const digits = '0123456789abcdef';
    const tmp = Buffer.allocUnsafe(8);
    for (let i = 7; i >= 0; i--) {
      tmp[i] = digits.charCodeAt(value & 0xf);
      value >>>= 4;
    }
    this.writeBuffer(tmp, 0, 8);
  }
}

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

function generatePassword(length, pools, combined, out) {
  let position = 0;
  for (const pool of pools) {
    out[position++] = pool.charCodeAt(below(pool.length));
  }
  while (position < length) {
    out[position++] = combined.charCodeAt(below(combined.length));
  }

  for (let i = length - 1; i > 0; i--) {
    const j = below(i + 1);
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
}

function fnv1a(hash, data, length) {
  let h = hash;
  for (let i = 0; i < length; i++) {
    h ^= data[i];
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

  const combined = pools.join('');
  const password = Buffer.allocUnsafe(MAX_LENGTH);
  const out = new Output();
  let checksum = 2166136261;

  if (asJson) {
    out.writeString('{"passwords":[');
  }

  for (let index = 0; index < count; index++) {
    generatePassword(length, pools, combined, password);
    checksum = fnv1a(checksum, password, length);
    checksum = fnv1a(checksum, NEWLINE, 1);

    if (asJson) {
      if (index > 0) {
        out.writeByte(44);
      }
      out.writeByte(34);
      out.writeBuffer(password, 0, length);
      out.writeByte(34);
    } else {
      out.writeBuffer(password, 0, length);
      out.writeByte(10);
    }
  }

  if (asJson) {
    out.writeString('],"checksum":"');
    out.writeHex(checksum);
    out.writeString('"}\n');
  } else {
    out.writeString('checksum=');
    out.writeHex(checksum);
    out.writeByte(10);
  }

  out.flush();
  return 0;
}

process.exitCode = main(process.argv.slice(2));
