import { ArrowUpDown, SearchCheck, SearchX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { datasetFilesPath } from "@/constants/app-paths";
import type { HitView, RetrievalPage } from "@/services/retrieval-service";
import { HitCard } from "./hit-card";

interface Props {
  datasetId: string; chunkNum: number; started: boolean; data: RetrievalPage | null; running: boolean; page: number; displayPage: number;
  onPage: (page: number) => void; onReset: () => void; onSource: (hit: HitView, rank: number, trigger: HTMLElement) => void;
}
export function RetrievalResults({ datasetId, chunkNum, started, data, running, page, displayPage, onPage, onReset, onSource }: Props) {
  const { t, i18n } = useTranslation();
  if (!started) return <div data-testid="retrieval-idle"><EmptyState as="h2" icon={SearchCheck} heading={t("retrieval.idle.heading")} body={t("retrieval.idle.body")} /></div>;
  const format = (value: number | null) => value === null ? "—" : new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 0 }).format(value);
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / 10));
  return <section data-testid="retrieval-results" aria-busy={running || undefined} className="grid min-w-0 content-start gap-4">
    <header className="grid gap-2"><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold">{t("retrieval.results.title")}</h2>
      {data ? <p data-testid="retrieval-count" aria-live="polite" className="text-xs text-muted-foreground">{t("retrieval.results.count", { count: data.total })}</p> : null}
      {data?.rerankApplied ? <Badge variant="outline" data-testid="retrieval-reranked"><ArrowUpDown className="mr-1 size-3" aria-hidden="true" />{t("retrieval.results.reranked")}</Badge> : null}</div>
      {data ? <p data-testid="retrieval-timings" className="text-xs tabular-nums text-muted-foreground">{t(data.rerankApplied ? "retrieval.results.timingsRerank" : "retrieval.results.timings", { embed: format(data.timings.embedMs), search: format(data.timings.searchMs), rerank: format(data.timings.rerankMs) })}</p> : null}
    </header>
    {running && !data ? <div data-testid="retrieval-running" className="grid gap-4">{[0, 1, 2].map((n) => <Skeleton className="h-40 w-full" key={n} />)}</div> : null}
    {data && data.total === 0 ? chunkNum === 0 ? <Alert variant="info" data-testid="retrieval-no-chunks">{t("retrieval.noChunks")} <Link className="underline" to={datasetFilesPath(datasetId)}>{t("retrieval.noChunksLink")}</Link></Alert> : <div data-testid="retrieval-empty"><EmptyState as="h2" icon={SearchX} heading={t("retrieval.empty.heading")} body={t("retrieval.empty.body")} action={<Button type="button" variant="ghost" onClick={onReset}>{t("retrieval.reset")}</Button>} /></div> : null}
    {data?.hits.length ? <ol className="grid gap-4">{data.hits.map((hit, index) => <li key={hit.chunkId}><HitCard hit={hit} rank={(displayPage - 1) * 10 + index + 1} reranked={data.rerankApplied} onSource={(trigger) => onSource(hit, (displayPage - 1) * 10 + index + 1, trigger)} /></li>)}</ol> : null}
    <Pagination data-testid="retrieval-pages" aria-label={t("retrieval.results.pages")} page={page} pages={pages} onPageChange={onPage} previousLabel={t("common.pagination.previous")} nextLabel={t("common.pagination.next")} statusLabel={t("common.pagination.status", { page, pages })} />
  </section>;
}
