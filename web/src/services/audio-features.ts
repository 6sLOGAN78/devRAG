import { asRecord } from "./mapping";
export interface AudioView { start: number; end: number }
export function audioOf(raw: unknown): AudioView | undefined {
  const s = asRecord(raw);
  return typeof s.start === "number" && typeof s.end === "number" && Number.isFinite(s.start) && Number.isFinite(s.end) && 0 <= s.start && s.start < s.end && s.end <= 60 ? { start:s.start, end:s.end } : undefined;
}
