import { describe, expect, it } from 'vitest';
import { GUS_MODELS, getGusModel } from '../src/gus/catalog.generated';

describe('GUS UI model catalogue', () => {
  it('exposes only the two pinned small Apache-licensed models with provenance', () => {
    expect(GUS_MODELS.map((model) => model.id)).toEqual(['qwen25-05b-q4km', 'smollm2-360m-q4km']);
    expect(getGusModel('qwen25-05b-q4km')).toMatchObject({
      byteCount: 491400032,
      repository: 'Qwen/Qwen2.5-0.5B-Instruct-GGUF',
      revision: '9217f5db79a29953eb74d5343926648285ec7e67',
      sha256: '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db',
      licenseName: 'Apache License 2.0',
      attribution: 'Qwen2.5 model; GGUF repository maintained by Qwen',
    });
    expect(getGusModel('smollm2-360m-q4km')).toMatchObject({
      byteCount: 270590528,
      repository: 'mfuntowicz/SmolLM2-360M-Instruct-Q4_K_M-GGUF',
      revision: 'de67c694b3fa2c6e9b45b50f286b2555c5dee2a8',
      sha256: '8856952e27c65a87618f8347d1d06328c3953af04e8327b6dd1fab6670358fd0',
      licenseName: 'Apache License 2.0',
      attribution: 'SmolLM2 model family by HuggingFaceTB; GGUF uploaded/converted by mfuntowicz',
    });
    expect(getGusModel('unlisted-model')).toBeUndefined();
  });
});
