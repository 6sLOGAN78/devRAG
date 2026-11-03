import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useCanManageDataset } from "@/hooks/use-dataset-permissions";
import { updateDatasetChunking, type DatasetDetailView } from "@/services/dataset-service";
import { cancelDatasetJob, listDatasetJobs, startDatasetEnrichment, startDatasetRaptor } from "@/services/dataset-job-service";
import { useWorkspaceStore } from "@/stores/workspace-store";

export function DerivedJobs({ dataset }: { dataset: DatasetDetailView }) {
  const { t } = useTranslation();
  const canManage = useCanManageDataset(dataset);
  const current = useWorkspaceStore(state => state.activeTenantId === dataset.tenantId);
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const key = ["ws", dataset.tenantId, "dataset-jobs", dataset.id];
  const jobs = useQuery({ queryKey: key, queryFn: ({ signal }) => listDatasetJobs(dataset.id, signal),
    enabled: current && open, retry: false, refetchInterval: query => query.state.data?.some(job => job.status === "running") ? 2000 : false });
  if (!current) return null;

  async function start() {
    if (busy || !canManage || useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
    setBusy(true); setError(false);
    try { await startDatasetEnrichment(dataset.id); await client.invalidateQueries({ queryKey: key }); }
    catch { setError(true); }
    finally { if (useWorkspaceStore.getState().activeTenantId === dataset.tenantId) setBusy(false); }
  }

  async function startRaptor() {
    if (busy || !canManage || useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
    setBusy(true); setError(false);
    try {
      if (!dataset.parserConfig.raptor) await updateDatasetChunking(dataset.id, { raptor: true });
      if (useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
      await startDatasetRaptor(dataset.id);
      await client.invalidateQueries({ queryKey: key });
    } catch { setError(true); }
    finally { if (useWorkspaceStore.getState().activeTenantId === dataset.tenantId) setBusy(false); }
  }

  async function cancel() {
    if (!cancelId || busy || !canManage || useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
    setBusy(true); setError(false);
    try { await cancelDatasetJob(dataset.id, cancelId); await client.invalidateQueries({ queryKey: key }); setCancelId(null); }
    catch { setError(true); }
    finally { if (useWorkspaceStore.getState().activeTenantId === dataset.tenantId) setBusy(false); }
  }

  return <section className="grid gap-4 rounded-lg border bg-card p-4" data-testid="dataset-derived-jobs">
    <Button type="button" variant="ghost" className="justify-start" data-testid="dataset-jobs-open" aria-expanded={open} onClick={() => setOpen(value => !value)}>{t("datasets.jobs.title")}</Button>
    {open ? <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">{t("datasets.jobs.help")}</p>
      {canManage ? <div className="flex flex-wrap gap-2"><Button type="button" data-testid="dataset-jobs-start" disabled={busy || jobs.data?.some(job => job.status === "running")} onClick={() => void start()}>{t("datasets.jobs.start")}</Button><Button type="button" variant="outline" data-testid="dataset-raptor-start" disabled={busy || jobs.data?.some(job => job.status === "running")} onClick={() => void startRaptor()}>{t("datasets.jobs.raptorStart")}</Button></div> : null}
      {jobs.isPending ? <p role="status">{t("datasets.jobs.loading")}</p> : null}
      {jobs.isError ? <Alert role="alert">{t("datasets.jobs.failed")} <Button type="button" variant="outline" onClick={() => void jobs.refetch()}>{t("datasets.jobs.retry")}</Button></Alert> : null}
      {jobs.data?.length === 0 ? <p>{t("datasets.jobs.empty")}</p> : null}
      {jobs.data?.map(job => <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3" data-testid="dataset-job-row">
        <div><p className="text-sm font-medium">{t(job.type === "raptor" ? "datasets.jobs.raptor" : "datasets.jobs.enrich")}</p><p className="text-xs text-muted-foreground" data-testid="dataset-job-progress">{t(`datasets.jobs.status.${job.status}`)} · {t(job.type === "raptor" ? "datasets.jobs.countsRaptor" : "datasets.jobs.counts", { completed: job.completed, total: job.total, failed: job.failed })}</p></div>
        {canManage && job.status === "running" ? <Button type="button" variant="outline" disabled={busy} onClick={() => setCancelId(job.id)}>{t("datasets.jobs.cancel")}</Button> : null}
      </div>)}
      {error ? <Alert role="alert">{t("datasets.jobs.failed")}</Alert> : null}
    </div> : null}
    <AlertDialog open={cancelId !== null} onOpenChange={value => { if (!value && !busy) setCancelId(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t(jobs.data?.find(job => job.id === cancelId)?.type === "raptor" ? "datasets.jobs.cancelRaptorTitle" : "datasets.jobs.cancelTitle")}</AlertDialogTitle><AlertDialogDescription>{t(jobs.data?.find(job => job.id === cancelId)?.type === "raptor" ? "datasets.jobs.cancelRaptorHelp" : "datasets.jobs.cancelHelp")}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("datasets.jobs.keep")}</AlertDialogCancel><AlertDialogAction asChild><Button type="button" disabled={busy} onClick={event => { event.preventDefault(); void cancel(); }}>{t("datasets.jobs.cancel")}</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>;
}
