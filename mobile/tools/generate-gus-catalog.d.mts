type GusCatalogModel = {
  id: string; name: string; repository: string; filename: string; revision: string; url: string;
  byteCount: number; sha256: string; licenseName: string; licenseUrl: string; attribution: string;
  supportedLanguages?: string[]; appContextLimit?: number; limitations?: string[];
};
type GusCatalogDocument = { schema: number; models: GusCatalogModel[] };
export function validateCatalog(value: GusCatalogDocument): GusCatalogModel[];
export function generateCatalogSource(value: GusCatalogDocument): string;
export function generateJavaCatalogSource(value: GusCatalogDocument): string;
export function generateSwiftCatalogSource(value: GusCatalogDocument): string;
