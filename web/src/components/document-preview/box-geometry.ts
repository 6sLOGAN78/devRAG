import type { ChunkPosition } from "@/services/chunk-service";

/** A box on a page as CSS percent strings of the page wrapper. */
export interface BoxStyle {
  left: string;
  top: string;
  width: string;
  height: string;
}

/** A box is never drawn smaller than this on screen, so a one-line chunk stays findable (UI-SPEC spacing exceptions). */
export const MIN_BOX_PX = 4;

const percent = (value: number): string => `${Number(value.toFixed(4))}%`;

const isSize = (value: number): boolean => Number.isFinite(value) && value > 0;

/**
 * The place of a position on its page as percent of the page's width and height (R-164). Positions are PDF points at
 * zoom 1 with the origin at the top left and `pageSize` is the same page in the same unit, so the result does not depend
 * on the rendered image, the zoom or the window. The box is clipped to the page.
 *
 * Returns null, and so draws nothing, for a missing or unusable page size, a non-finite number, a box without area or a
 * box wholly outside the page: numbers from the server never reach a style string unvalidated (T-04-30-02).
 */
export function boxStyle(position: ChunkPosition, pageSize: readonly [number, number] | undefined): BoxStyle | null {
  if (pageSize === undefined) return null;
  const [width, height] = pageSize;
  if (!isSize(width) || !isSize(height)) return null;
  const { x0, x1, top, bottom } = position;
  if (![x0, x1, top, bottom].every(Number.isFinite)) return null;
  if (x1 <= x0 || bottom <= top) return null;
  const left = Math.max(0, x0);
  const right = Math.min(width, x1);
  const upper = Math.max(0, top);
  const lower = Math.min(height, bottom);
  if (right <= left || lower <= upper) return null;
  return {
    left: percent((left / width) * 100),
    top: percent((upper / height) * 100),
    width: percent(((right - left) / width) * 100),
    height: percent(((lower - upper) / height) * 100),
  };
}
