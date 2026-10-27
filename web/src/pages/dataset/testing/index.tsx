import { ChevronLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { SourceDrawer } from "@/components/source-drawer";
import { sourceFromHit, type SourceView } from "@/components/source-drawer/source-model";
import { Alert } from "@/components/ui/alert";
import { datasetFilesPath } from "@/constants/app-paths";
import { useDatasetBinding } from "@/hooks/use-dataset-binding";
import { useModelsRequest } from "@/hooks/use-llm-request";
import { useRetrievalResults } from "@/hooks/use-retrieval-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { DatasetDetailView } from "@/services/dataset-service";
import type { RetrievalPage } from "@/services/retrieval-service";
import { DatasetNotFound, DatasetPageSkeleton } from "../page-states";
import { retrievalFailure } from "./errors";
import { RetrievalControls, type RetrievalValues } from "./retrieval-controls";
import { RetrievalResults } from "./retrieval-results";

const defaults = (): RetrievalValues => ({ question: "", threshold: 0.2, weight: 0.3, rerankId: "" });
function BoundPage({ dataset, refetchDataset }: { dataset: DatasetDetailView; refetchDataset: () => void }) {
  const { t } = useTranslation(), workspace = useActiveWorkspace();
  const [values, setValues] = useState(defaults), [submitted, setSubmitted] = useState<RetrievalValues | null>(null);
  const [page, setPage] = useState(1), [runId, setRunId] = useState(0), [source, setSource] = useState<SourceView | null>(null);
  const trigger = useRef<HTMLElement | null>(null), root = useRef<HTMLDivElement>(null);
  const models = useModelsRequest("rerank");
  const input = submitted ? { question: submitted.question.trim(), similarityThreshold: submitted.threshold, vectorSimilarityWeight: submitted.weight, rerankId: submitted.rerankId, size: 10 } : null;
  const result = useRetrievalResults(dataset.id, input, page, runId, true);
  const last = useRef<{ data: RetrievalPage; page: number } | null>(null);
  if (result.data && !result.isPlaceholderData) last.current = { data: result.data, page };
  const data = result.data ?? last.current?.data ?? null, displayPage = result.isPlaceholderData || !result.data ? last.current?.page ?? page : page;
  const failure = result.isError ? retrievalFailure(result.error) : null;
  const refetch = useRef(refetchDataset); refetch.current = refetchDataset;
  useEffect(() => { if (failure?.key === "workspace.forbidden") refetch.current(); }, [result.error]);
  const stale = submitted !== null && JSON.stringify(values) !== JSON.stringify(submitted);
  const reset = () => setValues((current) => ({ ...defaults(), question: current.question }));
  if (failure?.kind === "not-found") return <div data-testid="retrieval-not-found"><DatasetNotFound /></div>;
  return <div ref={root} data-testid="retrieval-page" className="grid gap-6">
    <Link data-testid="retrieval-back" to={datasetFilesPath(dataset.id)} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="size-4" aria-hidden="true" />{dataset.name}</Link>
    <PageHeader title={t("retrieval.title")} /><p className="text-sm text-muted-foreground">{t("retrieval.intro", { dataset: dataset.name })}</p>
    <div className="flex min-w-0 flex-col gap-6 lg:flex-row">
      <RetrievalControls values={values} onChange={setValues} onReset={reset} models={models.data ?? []} running={result.isFetching} dirtyAfterRun={stale}
        questionError={failure?.kind === "question" && !stale ? failure.key : undefined} onRun={() => { if (result.isFetching) return; setSubmitted({ ...values }); setPage(1); setRunId((n) => n + 1); }} />
      <div className="grid min-w-0 flex-1 content-start gap-4">
        {stale ? <Alert variant="info" data-testid="retrieval-stale">{t("retrieval.stale")}</Alert> : null}
        {failure?.kind === "alert" ? <Alert data-testid="retrieval-error">{t(failure.key, { workspace: workspace?.name })}</Alert> : null}
        {models.isError ? <ErrorState noun={t("retrieval.field.rerank")} onAction={() => void models.refetch()} /> : null}
        <RetrievalResults datasetId={dataset.id} chunkNum={dataset.chunkNum} started={submitted !== null} data={data} running={result.isFetching} page={page} displayPage={displayPage} onPage={setPage} onReset={reset}
          onSource={(hit, rank, opener) => { trigger.current = opener; setSource(sourceFromHit(hit, rank)); }} />
      </div>
    </div>
    <SourceDrawer source={source} open={source !== null} onOpenChange={(open) => { if (!open) setSource(null); }} onCloseAutoFocus={(event) => { event.preventDefault(); if (trigger.current?.isConnected) trigger.current.focus(); else root.current?.querySelector<HTMLElement>('[data-testid="field-retrieval-question"]')?.focus(); }} />
  </div>;
}
export default function RetrievalTestingPage() {
  const [params] = useSearchParams(), binding = useDatasetBinding({ datasetId: params.get("id") });
  const workspace = useActiveWorkspace();
  const { t, i18n } = useTranslation();
  useEffect(() => { document.title = binding.dataset ? t("retrieval.documentTitle", { name: binding.dataset.name }) : t("retrieval.title"); }, [binding.dataset, t, i18n.language]);
  if (binding.state === "not-found") return <div data-testid="retrieval-not-found"><DatasetNotFound /></div>;
  if (binding.state === "error") return <ErrorState heading={t("dataset.error.heading")} onAction={binding.refetch} />;
  if (!binding.bound || !binding.dataset || workspace?.tenantId !== binding.dataset.tenantId) return <DatasetPageSkeleton />;
  return <BoundPage key={`${binding.dataset.tenantId}:${binding.dataset.id}`} dataset={binding.dataset} refetchDataset={binding.refetch} />;
}
