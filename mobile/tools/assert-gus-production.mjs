import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assets = path.join(root, 'dist', 'assets');
const forbidden = /ISYMOTRON_GUS_E2E_ONLY_DO_NOT_SHIP_4F31|e2e-mock/i;
for (const entry of await readdir(assets, { withFileTypes: true })) {
  if (!entry.isFile()) continue;
  const bytes = await readFile(path.join(assets, entry.name));
  if (forbidden.test(entry.name) || forbidden.test(bytes.toString('utf8'))) {
    throw new Error(`GUS e2e-only mock leaked into production asset: ${entry.name}`);
  }
}
process.stdout.write('production GUS bundle contains no e2e mock marker\n');
