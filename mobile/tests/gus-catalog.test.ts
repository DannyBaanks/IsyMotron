import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { generateCatalogSource, validateCatalog } from '../tools/generate-gus-catalog.mjs';

const catalog = JSON.parse(readFileSync(new URL('../catalog/gus-models.json', import.meta.url), 'utf8'));

describe('GUS catalogue source', () => {
  it('generates the checked-in TypeScript from the sole JSON source', () => {
    const generated = readFileSync(new URL('../src/gus/catalog.generated.ts', import.meta.url), 'utf8');
    expect(generated).toBe(generateCatalogSource(catalog));
  });

  it('pins the two curated entries at immutable HTTPS revisions', () => {
    const models = validateCatalog(catalog);
    expect(models.map((model) => model.id)).toEqual(['qwen25-05b-q4km', 'smollm2-360m-q4km']);
    for (const model of models) {
      expect(model.revision).toMatch(/^[a-f0-9]{40}$/);
      expect(model.url).toMatch(/^https:\/\/huggingface\.co\/.+\/resolve\/[a-f0-9]{40}\/.+\.gguf$/);
      expect(model.licenseName).toBe('Apache License 2.0');
      expect(model.byteCount).toBeLessThan(500_000_000);
    }
  });

  it.each([
    ['malformed SHA-256', (copy: any) => { copy.models[0].sha256 = 'ABC'; }],
    ['mutable main revision', (copy: any) => { copy.models[0].revision = 'main'; }],
    ['mutable latest revision', (copy: any) => { copy.models[0].revision = 'latest'; }],
    ['non-HTTPS URL', (copy: any) => { copy.models[0].url = copy.models[0].url.replace('https:', 'http:'); }],
    ['duplicate model ID', (copy: any) => { copy.models[1].id = copy.models[0].id; }],
  ])('rejects %s', (_case, mutate) => {
    const copy = structuredClone(catalog);
    mutate(copy);
    expect(() => validateCatalog(copy)).toThrow();
  });
});
