import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { generateCatalogSource, generateJavaCatalogSource, validateCatalog } from '../tools/generate-gus-catalog.mjs';

const catalog = JSON.parse(readFileSync(new URL('../catalog/gus-models.json', import.meta.url), 'utf8'));

describe('GUS catalogue source', () => {
  it('generates the checked-in TypeScript from the sole JSON source', () => {
    const generated = readFileSync(new URL('../src/gus/catalog.generated.ts', import.meta.url), 'utf8');
    expect(generated).toBe(generateCatalogSource(catalog));
  });

  it('emits 64-bit byte counts as Java long literals', () => {
    expect(generateJavaCatalogSource(catalog)).toContain('2837072864L');
  });

  it('pins curated entries at immutable HTTPS revisions', () => {
    const models = validateCatalog(catalog);
    expect(models.map((model) => model.id)).toEqual(['qwen25-05b-q4km', 'smollm2-360m-q4km', 'nemotron3-nano-4b-q4km']);
    for (const model of models) {
      expect(model.revision).toMatch(/^[a-f0-9]{40}$/);
      expect(model.url).toMatch(/^https:\/\/huggingface\.co\/.+\/resolve\/[a-f0-9]{40}\/.+\.gguf$/);
      expect(model.licenseName).toBeTruthy();
      expect(model.byteCount).toBeLessThanOrEqual(3_000_000_000);
    }
    const [qwen, smol, nemotron] = models;
    expect(qwen?.byteCount).toBeLessThan(500_000_000);
    expect(smol?.byteCount).toBeLessThan(500_000_000);
    expect(nemotron).toMatchObject({
      repository: 'nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF',
      revision: 'ba223d14e45525f7fae81db77ea8cabeb2fc6c25',
      byteCount: 2_837_072_864,
      sha256: 'be5d9a656a51922f24f1f09a759cebb694e1f5d9728bf0ef9f8c972c5a0b5ef2',
      licenseName: 'NVIDIA Nemotron Open Model License',
      supportedLanguages: ['English', 'code'],
      appContextLimit: 2048,
    });
    expect(nemotron?.limitations?.some((note) => note.includes('2.84 GB'))).toBe(true);
    expect(nemotron?.limitations?.some((note) => note.includes('español'))).toBe(true);
    expect(nemotron?.limitations?.some((note) => note.includes('NOT DEMONSTRATED'))).toBe(true);
  });

  it.each([
    ['malformed SHA-256', (copy: any) => { copy.models[0].sha256 = 'ABC'; }],
    ['mutable main revision', (copy: any) => { copy.models[0].revision = 'main'; }],
    ['mutable latest revision', (copy: any) => { copy.models[0].revision = 'latest'; }],
    ['non-HTTPS URL', (copy: any) => { copy.models[0].url = copy.models[0].url.replace('https:', 'http:'); }],
    ['duplicate model ID', (copy: any) => { copy.models[1].id = copy.models[0].id; }],
    ['model above the 3 GB safety ceiling', (copy: any) => { copy.models[0].byteCount = 3_000_000_001; }],
    ['malformed device limitations', (copy: any) => { copy.models[2]!.limitations = ['']; }],
  ])('rejects %s', (_case, mutate) => {
    const copy = structuredClone(catalog);
    mutate(copy);
    expect(() => validateCatalog(copy)).toThrow();
  });
});
