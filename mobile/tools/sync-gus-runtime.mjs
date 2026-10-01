#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const vendorDir = path.join(root, 'vendor', 'gus-runtime');
const sourcePin = '9c8a659840045cb31da7b501022645a194f4422d';
const llamaPin = '842b1880415d6f508f03b789e5ce70194def7bfd';
const pins = {
  'Sources/Model/GUSLlamaBridge.c': { sha256: 'b79fb3e4a50a5d8d7393e56aeefe1187dc20ca8ebaaf100d116dc0ed32029efb', url: `https://raw.githubusercontent.com/DannyBaanks/iSyCodeMovil/${sourcePin}/Sources/Model/GUSLlamaBridge.c` },
  'Sources/Model/GUSLlamaBridge.h': { sha256: 'c521205b8d5e4a7f796cc9db22e9ffdaac6f7505a73efd2e623d264f64af2353', url: `https://raw.githubusercontent.com/DannyBaanks/iSyCodeMovil/${sourcePin}/Sources/Model/GUSLlamaBridge.h` },
  LICENSE: { sha256: 'c005af3d1347d7169264c32e93a138324fcdd0da46dfbe85fcc06654982cf5fe', url: `https://raw.githubusercontent.com/DannyBaanks/iSyCodeMovil/${sourcePin}/LICENSE` },
  'LLAMA_CPP_LICENSE.txt': { sha256: '94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d', url: `https://raw.githubusercontent.com/ggml-org/llama.cpp/${llamaPin}/LICENSE` },
};

const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const expectedManifest = {
  schema: 1,
  source: { repository: 'https://github.com/DannyBaanks/iSyCodeMovil', revision: sourcePin },
  llamaCpp: { repository: 'https://github.com/ggml-org/llama.cpp', revision: llamaPin },
  files: Object.fromEntries(Object.entries(pins).map(([file, pin]) => [file, pin.sha256])),
};

async function readAndVerify() {
  const manifest = JSON.parse(await readFile(path.join(vendorDir, 'VENDOR.json'), 'utf8'));
  if (JSON.stringify(manifest) !== JSON.stringify(expectedManifest)) throw new Error('VENDOR.json differs from the reviewed fixed pins');
  for (const [relativePath, pin] of Object.entries(pins)) {
    const bytes = await readFile(path.join(vendorDir, relativePath));
    if (sha256(bytes) !== pin.sha256) throw new Error(`pinned hash mismatch: ${relativePath}`);
  }
}

async function fetchPins() {
  const contents = new Map();
  for (const [relativePath, pin] of Object.entries(pins)) {
    const response = await fetch(pin.url, { redirect: 'follow' });
    if (!response.ok) throw new Error(`could not fetch ${relativePath}: HTTP ${response.status}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (sha256(bytes) !== pin.sha256) throw new Error(`upstream hash mismatch: ${relativePath}`);
    contents.set(relativePath, bytes);
  }
  return contents;
}

const mode = process.argv[2];
if (mode === '--verify') {
  await readAndVerify();
  process.stdout.write('pinned GUS runtime snapshot verified\n');
} else if (mode === '--check') {
  await readAndVerify();
  const upstream = await fetchPins();
  for (const [relativePath, bytes] of upstream) {
    if (!bytes.equals(await readFile(path.join(vendorDir, relativePath)))) throw new Error(`snapshot differs from pinned upstream: ${relativePath}`);
  }
  process.stdout.write('pinned upstream GUS runtime snapshot matches\n');
} else if (mode === '--sync') {
  const upstream = await fetchPins();
  for (const [relativePath, bytes] of upstream) {
    const destination = path.join(vendorDir, relativePath);
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, bytes);
  }
  await readAndVerify();
  process.stdout.write('updated allowlisted GUS runtime snapshot\n');
} else {
  throw new Error('usage: node tools/sync-gus-runtime.mjs --verify|--check|--sync');
}
