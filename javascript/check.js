'use strict';

// Build check for the interpreted JavaScript implementation.
//
// AltBench needs one build command that parses every source file, so that an
// edit to `rng.js` is actually observed. `node --check` only accepts one file
// per process, therefore this helper compiles both entry points in one Node
// process with the same parser used for module loading.

const fs = require('node:fs');
const vm = require('node:vm');

for (const file of ['rng.js', 'passgen.js']) {
  const source = fs.readFileSync(file, 'utf8');
  new vm.Script(source, { filename: file });
}
