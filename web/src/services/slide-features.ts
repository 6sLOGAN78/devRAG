import { asRecord } from "./mapping";
export interface SlideView { number: number; title: string }
export function slideOf(raw: unknown): SlideView | undefined {
  const s = asRecord(raw);
  return Number.isSafeInteger(s.number) && (s.number as number) > 0 && (s.number as number) <= 20000 && typeof s.title === "string" && s.title.length <= 1024 ? {number:s.number as number,title:s.title} : undefined;
}
