import { SourceMarkdown } from "@/components/markdown-content/source-markdown";
import { StructuredTable } from "@/components/markdown-content/structured-table";
import { useQuery } from "@tanstack/react-query";
import { useBlobUrl } from "@/components/document-preview/use-blob-url";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { fetchDocumentAsset } from "@/services/page-service";
import type { DocumentAssetView } from "@/services/document-service";
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

function Figure({ asset, source, showCaption = true }: { asset: DocumentAssetView; source: SourceView; showCaption?: boolean }) {
  const { t } = useTranslation(), tenantId = useActiveWorkspace()?.tenantId ?? null;
  const query = useQuery({ queryKey: ["ws", tenantId, "document-asset", source.datasetId, source.docId, asset.id], queryFn: ({ signal }) => fetchDocumentAsset(asset.id, signal), retry: false, staleTime: 0, gcTime: 0, enabled: tenantId !== null });
  const url = useBlobUrl(tenantId === null || query.isError ? null : query.data);
  return <figure className="grid gap-2 rounded-md border p-3">
    {url ? <img data-testid="source-asset-image" src={url} alt={asset.caption || t("source.figure")} width={asset.width} height={asset.height} className="h-auto max-w-full" /> : query.isError ? <div role="status"><p>{t("source.figureUnavailable")}</p><Button variant="outline" onClick={() => void query.refetch()}>{t("source.retry")}</Button></div> : <Skeleton className="h-32 w-full" />}
    {showCaption && asset.caption ? <figcaption data-testid="source-asset-caption" className="whitespace-pre-wrap break-words text-sm">{asset.caption}</figcaption> : null}
  </figure>;
}

interface Props { source: SourceView | null; open: boolean; onOpenChange: (open: boolean) => void; onCloseAutoFocus?: (event: Event) => void }
function Body({ source, onCloseAutoFocus }: { source: SourceView; onCloseAutoFocus?: (event: Event) => void }) {
  const { t, i18n } = useTranslation(), passage = useRef<HTMLDivElement>(null);
  const firstPage = source.positions[0]?.page, [page, setPage] = useState(firstPage ?? 1);
  const markdown = /\.(md|markdown)$/i.test(source.docName);
  const detail = useDocumentDetailRequest(source.datasetId, source.docId);
  const tables = (source.tables ?? []).filter((table) => detail.data?.assets?.some((asset) => asset.kind === "table" && asset.id === table.assetId));
  const tableIds = new Set(tables.map((table) => table.assetId));
  const figures = (detail.data?.assets ?? []).filter((asset) => !tableIds.has(asset.id));
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
      <div className="grid gap-2"><h2 className="text-xs font-semibold">{t("source.passage")}</h2><div ref={passage} role="region" aria-label={t("source.passageLabel")} tabIndex={0} data-testid="source-passage" className={`${markdown ? "max-h-[65vh]" : "max-h-60"} overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background p-4 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}>{markdown ? <SourceMarkdown text={source.content} /> : source.content}</div></div>
      {!gone && tables.length ? <section aria-label={t("source.tables")} className="grid gap-4">{tables.map((table, index) => <div key={`${table.assetId}:${index}`}><StructuredTable table={table} /><p className="mb-2 text-xs font-semibold">{t("source.crop")}</p><Figure asset={detail.data!.assets!.find((asset) => asset.id === table.assetId)!} source={source} showCaption={false} /></div>)}</section> : null}
      {!gone && figures.length ? <section aria-label={t("source.figures")} className="grid gap-3"><h2 className="text-xs font-semibold">{t("source.figures")}</h2>{figures.map((asset) => <Figure key={asset.id} asset={asset} source={source} />)}</section> : null}
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
