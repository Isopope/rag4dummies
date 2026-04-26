export type CellValue = string | number | boolean | null | undefined | Date | object;

export function isNumericColumn(data: Record<string, CellValue>[], column: string): boolean {
  let numericCount = 0;
  let nonNullCount = 0;
  for (const row of data) {
    const v = row[column];
    if (v === null || v === undefined || v === '') continue;
    nonNullCount++;
    if (typeof v === 'number' && !Number.isNaN(v)) {
      numericCount++;
    } else if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) {
      numericCount++;
    }
  }
  return nonNullCount > 0 && numericCount / nonNullCount >= 0.8;
}

export function formatCellValue(value: CellValue): string {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return value.toLocaleString();
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
