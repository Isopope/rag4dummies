export interface RangeOption {
  label: string;
  days: number | null; // null = all
}

export type RangeOptions = Record<string, RangeOption>;

export const DATE_RANGE_OPTIONS: RangeOptions = {
  '1d': { label: '24h', days: 1 },
  '7d': { label: '7 jours', days: 7 },
  '30d': { label: '30 jours', days: 30 },
  '90d': { label: '90 jours', days: 90 },
  '1y': { label: '1 an', days: 365 },
  all: { label: 'Tout', days: null },
};

export type DateRange = keyof typeof DATE_RANGE_OPTIONS;

export const labelize = (key: string): string =>
  key
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();

export const toKey = (value: string): string =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, '_');

const parseDate = (v: unknown): Date | null => {
  if (v instanceof Date) return v;
  if (typeof v === 'string' || typeof v === 'number') {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return null;
};

export function sortByDateKey<T extends Record<string, unknown>>(
  data: T[],
  key: string,
): T[] {
  return [...data].sort((a, b) => {
    const da = parseDate(a[key])?.getTime() ?? 0;
    const db = parseDate(b[key])?.getTime() ?? 0;
    return da - db;
  });
}

export function filterByDateRange<T extends Record<string, unknown>>(
  data: T[],
  key: string,
  range: string,
): T[] {
  const opt = DATE_RANGE_OPTIONS[range];
  if (!opt || opt.days === null) return data;
  const cutoff = Date.now() - opt.days * 24 * 60 * 60 * 1000;
  return data.filter((row) => {
    const d = parseDate(row[key]);
    return d ? d.getTime() >= cutoff : true;
  });
}

export function formatNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
