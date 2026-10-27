/**
 * Small coercions shared by the service mappers. Every mapper copies an explicit field list and reads each field
 * through these, so an unexpected field or type from the server never reaches component state.
 */

export const text = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
};

export const count = (value: unknown): number => {
  const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
};

export const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {});

/** A whole number within [low, high]; NaN and infinity become `low`. */
export function clampWhole(value: number, low: number, high: number): number {
  if (!Number.isFinite(value)) return low;
  return Math.min(high, Math.max(low, Math.floor(value)));
}
/** Valid one-based inclusive PDF ranges; malformed wire values never reach the form. */
export function pageRangesOf(raw: unknown): [number, number][] {
  if (!Array.isArray(raw) || raw.length > 128) return [];
  const result: [number, number][] = [];
  for (const pair of raw) {
    if (!Array.isArray(pair) || pair.length !== 2 || !pair.every((n) => Number.isSafeInteger(n)) || pair[0] < 1 || pair[1] < pair[0] || pair[1] > 1000000) return [];
    result.push([pair[0], pair[1]]);
  }
  return result;
}
