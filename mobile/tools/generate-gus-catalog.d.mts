type GusCatalogDocument = { schema: number; models: Record<string, unknown>[] };
export function validateCatalog(value: GusCatalogDocument): GusCatalogDocument['models'];
export function generateCatalogSource(value: GusCatalogDocument): string;
export function generateJavaCatalogSource(value: GusCatalogDocument): string;
