#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const uiRoot = join(fileURLToPath(new URL('.', import.meta.url)), '..');

const GUARDED_DIRS = [
  join(uiRoot, 'src/desktop'),
  join(uiRoot, 'src/navigation'),
  join(uiRoot, 'src/components/ui'),
  join(uiRoot, 'src/components'),
  join(uiRoot, 'src/pages'),
];

const IGNORE_FILES = new Set([
  'src/components/PremiumLoginShell.tsx',
]);

const SLATE_CLASS = /(?:^|[\s"'`{])(?:[a-z]+:)?(?:hover:|focus:|active:)?(?:text|bg|border|divide|ring|from|to|via)-slate-/;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(tsx|ts|css)$/.test(name)) out.push(path);
  }
  return out;
}

const violations = [];
for (const dir of GUARDED_DIRS) {
  for (const file of walk(dir)) {
    const content = readFileSync(file, 'utf8');
    const rel = relative(uiRoot, file);
    if (IGNORE_FILES.has(rel)) continue;
    if (SLATE_CLASS.test(content)) violations.push(rel);
  }
}

if (violations.length > 0) {
  console.error(`Hardcoded slate-* utilities found (${violations.length} files):\n`);
  for (const file of violations.slice(0, 40)) console.error(`  ${file}`);
  process.exit(1);
}

console.log('UI token check passed.');
