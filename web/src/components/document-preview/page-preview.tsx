import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChunkPosition } from "@/services/chunk-service";
import { MIN_BOX_PX, boxStyle, type BoxStyle } from "./box-geometry";
import { usePageImage } from "./use-page-image";

/** Zoom levels as percent of the pane's width. The server renders at zoom 3, so 300 percent of a 500px pane is still sharp. */
export const ZOOM_LEVELS = [100, 150, 200, 300] as const;
const DEFAULT_ZOOM = ZOOM_LEVELS[0];
/** Width over height of an A4 page, used until the real page size is known. */
const FALLBACK_ASPECT = "1 / 1.414";

/** The chunk whose boxes are drawn: its place on the pages, and its number for the announcement. */
export interface PreviewSelection {
  chunkId: string;
  /** Position of the chunk in the current result. */
  number: number;
  positions: ChunkPosition[];
}

export interface PagePreviewProps {
  datasetId: string;
  docId: string;
  /** The document's name, for the image's description. */
  name: string;
  /** Number of pages; 0, null or a non-number renders nothing. */
  pages: number | null;
  /** The page shown (1-based, clamped into 1..pages). */
  page: number;
  onPageChange: (page: number) => void;
  /** The selected chunk, or null for none (the page is then shown without boxes). */
  selection?: PreviewSelection | null;
  /** `{page: [width, height]}` in the unit of the positions. */
  pageSizes?: Record<string, [number, number]>;
  /** False until the workspace is bound (FE-02). */
  enabled?: boolean;
  className?: string;
}

const isUsableSize = (size: readonly number[] | undefined): size is [number, number] => size !== undefined && size.length === 2 && size.every((n) => Number.isFinite(n) && n > 0);

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * One page of a document as an image with the selected chunk's boxes over it (UI-16). Boxes are absolutely positioned in
 * percent of a wrapper whose aspect ratio is the page's, so zoom and window size cannot misalign them (R-164). Boxes are
 * hidden from assistive technology and ignore the pointer; the link between a chunk and its place is also said in words.
 */
export function PagePreview({ datasetId, docId, name, pages, page, onPageChange, selection = null, pageSizes = {}, enabled = true, className }: PagePreviewProps) {
  const { t } = useTranslation();
  const total = typeof pages === "number" && Number.isFinite(pages) ? Math.floor(pages) : 0;
  const shown = Math.min(Math.max(1, Math.floor(Number.isFinite(page) ? page : 1)), Math.max(1, total));
  const [zoom, setZoom] = useState<number>(DEFAULT_ZOOM);
  const [natural, setNatural] = useState<{ page: number; size: [number, number] } | null>(null);
  const firstBox = useRef<HTMLDivElement | null>(null);
  const image = usePageImage(datasetId, docId, shown, enabled && total > 0);

  const size = pageSizes[String(shown)];
  const known = isUsableSize(size) ? size : natural?.page === shown ? natural.size : undefined;
  const aspect = known === undefined ? FALLBACK_ASPECT : `${known[0]} / ${known[1]}`;

  const positions = selection?.positions ?? [];
  const boxes: BoxStyle[] = [];
  for (const position of positions) {
    if (position.page !== shown) continue;
    const style = boxStyle(position, isUsableSize(size) ? size : undefined);
    if (style !== null) boxes.push(style);
  }
  const hasBoxes = boxes.length > 0;

  const chunkId = selection?.chunkId;
  useEffect(() => {
    if (chunkId === undefined || !hasBoxes) return;
    const element = firstBox.current;
    // Older engines and test DOMs have no scrollIntoView: the box is then simply not centred.
    if (element !== null && typeof element.scrollIntoView === "function") element.scrollIntoView({ block: "center", inline: "center", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [chunkId, shown, hasBoxes]);

  if (total < 1) return null;

  const firstPage = positions[0]?.page;
  const onThisPage = positions.some((position) => position.page === shown);
  let live = "";
  if (selection !== null) live = firstPage === undefined ? t("inspector.live.selectedNoPage", { n: selection.number }) : t("inspector.live.selected", { n: selection.number, page: firstPage });

  const atStart = shown <= 1;
  const atEnd = shown >= total;
  const zoomIndex = Math.max(0, ZOOM_LEVELS.indexOf(zoom as (typeof ZOOM_LEVELS)[number]));
  const atMinZoom = zoomIndex <= 0;
  const atMaxZoom = zoomIndex >= ZOOM_LEVELS.length - 1;

  return (
    <Card role="region" aria-label={t("inspector.preview.region")} data-testid="page-preview" className={cn("flex min-h-0 flex-col gap-3 p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav aria-label={t("inspector.preview.pagesNav")} className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="preview-prev"
            aria-label={t("inspector.preview.previous")}
            aria-disabled={atStart}
            className={cn(atStart && "opacity-50")}
            onClick={() => !atStart && onPageChange(shown - 1)}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <span data-testid="preview-caption" aria-live="polite" className="text-xs font-normal tabular-nums text-muted-foreground">
            {t("inspector.preview.caption", { page: shown, pages: total })}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="preview-next"
            aria-label={t("inspector.preview.next")}
            aria-disabled={atEnd}
            className={cn(atEnd && "opacity-50")}
            onClick={() => !atEnd && onPageChange(shown + 1)}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </nav>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="preview-zoom-out"
            aria-label={t("inspector.preview.zoomOut")}
            aria-disabled={atMinZoom}
            className={cn(atMinZoom && "opacity-50")}
            onClick={() => !atMinZoom && setZoom(ZOOM_LEVELS[zoomIndex - 1] ?? DEFAULT_ZOOM)}
          >
            <ZoomOut aria-hidden="true" />
          </Button>
          <span data-testid="preview-zoom-level" className="min-w-10 text-center text-xs font-normal tabular-nums text-muted-foreground">
            {t("inspector.preview.zoomLevel", { percent: zoom })}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            data-testid="preview-zoom-in"
            aria-label={t("inspector.preview.zoomIn")}
            aria-disabled={atMaxZoom}
            className={cn(atMaxZoom && "opacity-50")}
            onClick={() => !atMaxZoom && setZoom(ZOOM_LEVELS[zoomIndex + 1] ?? DEFAULT_ZOOM)}
          >
            <ZoomIn aria-hidden="true" />
          </Button>
          <Button type="button" variant="ghost" size="sm" data-testid="preview-fit" onClick={() => setZoom(DEFAULT_ZOOM)}>
            {t("inspector.preview.fit")}
          </Button>
        </div>
      </div>

      <p role="status" data-testid="chunk-live" className="sr-only">
        {live}
      </p>

      {selection !== null && positions.length === 0 ? (
        <p data-testid="preview-away-note" className="text-xs font-normal text-muted-foreground">
          {t("inspector.preview.noPlace")}
        </p>
      ) : null}
      {selection !== null && positions.length > 0 && !onThisPage && firstPage !== undefined ? (
        <p data-testid="preview-away-note" className="flex flex-wrap items-center gap-x-2 text-xs font-normal text-muted-foreground">
          <span>{t("inspector.preview.away", { page: firstPage })}</span>
          <Button type="button" variant="link" size="sm" data-testid="preview-goto" className="h-auto p-0 text-xs" onClick={() => onPageChange(firstPage)}>
            {t("inspector.preview.goto", { page: firstPage })}
          </Button>
        </p>
      ) : null}

      <div data-testid="preview-scroll" tabIndex={0} className="min-h-0 flex-1 overflow-auto rounded-md border bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <div className="relative" style={{ width: `${zoom}%`, aspectRatio: aspect }}>
          {image.url !== null ? (
            <img
              src={image.url}
              alt={t("inspector.preview.alt", { page: shown, name })}
              draggable={false}
              data-testid="preview-image"
              className="size-full select-none"
              onLoad={(event) => {
                const { naturalWidth, naturalHeight } = event.currentTarget;
                if (naturalWidth > 0 && naturalHeight > 0) setNatural({ page: shown, size: [naturalWidth, naturalHeight] });
              }}
            />
          ) : image.isError ? (
            <div data-testid="preview-error" role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm font-normal">
              <p>{t("inspector.preview.error", { page: shown })}</p>
              <Button type="button" variant="ghost" size="sm" onClick={image.refetch}>
                {t("errorState.action")}
              </Button>
            </div>
          ) : (
            <Skeleton data-testid="preview-skeleton" aria-hidden="true" className="absolute inset-0 size-full rounded-none" />
          )}
          {boxes.map((style, index) => (
            <div
              key={index}
              ref={index === 0 ? firstBox : undefined}
              data-testid="preview-box"
              aria-hidden="true"
              className="absolute rounded-sm border-2 border-primary bg-primary/15"
              style={{ left: style.left, top: style.top, width: style.width, height: style.height, minWidth: `${MIN_BOX_PX}px`, minHeight: `${MIN_BOX_PX}px`, pointerEvents: "none" }}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}
