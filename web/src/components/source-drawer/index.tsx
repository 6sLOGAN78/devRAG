import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { PagePreview } from "@/components/document-preview/page-preview";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { documentViewerPath } from "@/constants/app-paths";
import { useDocumentDetailRequest } from "@/hooks/use-document-request";
import { ApiError } from "@/services/http";
import type { SourceView } from "./source-model";

interface Props { source: SourceView | null; open: boolean; onOpenChange: (open: boolean) => void; onCloseAutoFocus?: (event: Event) => void }
function Body({ source, onCloseAutoFocus }: { source: SourceView; onCloseAutoFocus?: (event: Event) => void }) {
  const { t, i18n } = useTranslation(), passage = useRef<HTMLDivElement>(null);
  const firstPage = source.positions[0]?.page, [page, setPage] = useState(firstPage ?? 1);
  const detail = useDocumentDetailRequest(source.datasetId, source.docId);
  const gone = detail.error instanceof ApiError && detail.error.status === 404;
  const pages = [...new Set(source.positions.map((position) => position.page))].sort((a, b) => a - b);
  const preview = !gone && source.positions.length > 0 && detail.data?.preview === "pages" && (detail.data.pagesTotal ?? 0) > 0;
  const loadingPreview = !gone && source.positions.length > 0 && /\.pdf$/i.test(source.docName) && detail.isPending;
  const size = source.pageSizes[String(firstPage)], aspect = size && size.every((value) => value > 0 && Number.isFinite(value)) ? `${size[0]} / ${size[1]}` : "1 / 1.414";
  const number = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <SheetContent side="right" closeLabel={t("source.close")} data-testid="source-drawer" onCloseAutoFocus={onCloseAutoFocus} onOpenAutoFocus={(event) => { event.preventDefault(); passage.current?.focus(); }}>
    <SheetHeader><SheetTitle data-testid="source-title">{t(source.kind === "chat" ? "source.title" : "source.titleHit", { n: source.number })}</SheetTitle><SheetDescription data-testid="source-document" className="break-all">{source.docName}</SheetDescription></SheetHeader>
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      <dl className="flex flex-wrap gap-4">
        {pages.length ? <div><dt className="text-xs font-semibold text-muted-foreground">{t("source.pages")}</dt><dd data-testid="source-pages" className="font-semibold tabular-nums">{pages.join(", ")}</dd></div> : null}
        {(["overall", "term", "vector", "rerank"] as const).map((key) => source.scores[key] !== null && Number.isFinite(source.scores[key]) ? <div key={key}><dt className="text-xs font-semibold text-muted-foreground">{t(`retrieval.score.${key}`)}</dt><dd data-testid={`source-score-${key}`} className="font-semibold tabular-nums">{number.format(source.scores[key]!)}</dd></div> : null)}
      </dl>
      <div className="grid gap-2"><h2 className="text-xs font-semibold">{t("source.passage")}</h2><div ref={passage} role="region" aria-label={t("source.passageLabel")} tabIndex={0} data-testid="source-passage" className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background p-4 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{source.content}</div></div>
      {gone ? <p data-testid="source-gone" className="text-sm text-muted-foreground">{t("source.gone")}</p> : null}
      {preview ? <div data-testid="source-preview"><PagePreview datasetId={source.datasetId} docId={source.docId} name={source.docName} pages={detail.data!.pagesTotal} page={page} onPageChange={setPage} selection={{ chunkId: source.chunkId, number: source.number, positions: source.positions }} pageSizes={source.pageSizes} /></div> : loadingPreview ? <div data-testid="source-preview" style={{ aspectRatio: aspect }}><Skeleton className="size-full" /></div> : null}
    </div>
    <div className="flex justify-end gap-2 border-t pt-4"><SheetClose asChild><Button variant="ghost" data-testid="source-close">{t("source.close")}</Button></SheetClose>
      {!gone ? <Button variant="outline" asChild><Link data-testid="source-open-document" to={documentViewerPath(source.datasetId, source.docId, firstPage)}>{t("source.open")}</Link></Button> : null}</div>
  </SheetContent>;
}
export function SourceDrawer({ source, open, onOpenChange, onCloseAutoFocus }: Props) {
  return <Sheet open={open && source !== null} onOpenChange={onOpenChange}>{open && source ? <Body key={`${source.kind}:${source.chunkId}:${source.number}`} source={source} onCloseAutoFocus={onCloseAutoFocus} /> : null}</Sheet>;
}
