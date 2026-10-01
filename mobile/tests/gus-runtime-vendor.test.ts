import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

const vendorRoot = new URL('../vendor/gus-runtime/', import.meta.url);
const manifest = JSON.parse(readFileSync(new URL('VENDOR.json', vendorRoot), 'utf8'));

const digest = (path: string) => createHash('sha256').update(readFileSync(new URL(path, vendorRoot))).digest('hex');

describe('pinned GUS runtime vendor snapshot', () => {
  it('records the reviewed iSyCode and llama.cpp source commits', () => {
    expect(manifest.source.repository).toBe('https://github.com/DannyBaanks/iSyCodeMovil');
    expect(manifest.source.revision).toBe('9c8a659840045cb31da7b501022645a194f4422d');
    expect(manifest.llamaCpp.revision).toBe('842b1880415d6f508f03b789e5ce70194def7bfd');
  });

  it('preserves the bridge source and both upstream license notices byte-for-byte', () => {
    expect(digest('Sources/Model/GUSLlamaBridge.c')).toBe('b79fb3e4a50a5d8d7393e56aeefe1187dc20ca8ebaaf100d116dc0ed32029efb');
    expect(digest('Sources/Model/GUSLlamaBridge.h')).toBe('c521205b8d5e4a7f796cc9db22e9ffdaac6f7505a73efd2e623d264f64af2353');
    expect(digest('LICENSE')).toBe('c005af3d1347d7169264c32e93a138324fcdd0da46dfbe85fcc06654982cf5fe');
    expect(digest('LLAMA_CPP_LICENSE.txt')).toBe('94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d');
    expect(manifest.files).toMatchObject({
      'Sources/Model/GUSLlamaBridge.c': 'b79fb3e4a50a5d8d7393e56aeefe1187dc20ca8ebaaf100d116dc0ed32029efb',
      'Sources/Model/GUSLlamaBridge.h': 'c521205b8d5e4a7f796cc9db22e9ffdaac6f7505a73efd2e623d264f64af2353',
      LICENSE: 'c005af3d1347d7169264c32e93a138324fcdd0da46dfbe85fcc06654982cf5fe',
      'LLAMA_CPP_LICENSE.txt': '94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d',
    });
  });

  it('verifies the vendored bytes without network access', () => {
    const output = execFileSync('node', ['tools/sync-gus-runtime.mjs', '--verify'], { encoding: 'utf8' });
    expect(output).toContain('verified');
  });
});
