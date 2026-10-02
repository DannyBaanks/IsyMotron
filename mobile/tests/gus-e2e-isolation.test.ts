import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('GUS E2E mock isolation', () => {
  it('loads the mock only under the explicit e2e Vite mode', async () => {
    const entry = await readFile(new URL('../src/main.ts', import.meta.url), 'utf8');
    expect(entry).toMatch(/import\.meta\.env\.MODE\s*===\s*["']e2e["']\s*\?\s*await import\(["']\.\/gus\/e2e-mock["']\)/);
  });
});
