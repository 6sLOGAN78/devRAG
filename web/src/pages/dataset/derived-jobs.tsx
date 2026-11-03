import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useCanManageDataset } from "@/hooks/use-dataset-permissions";
import { deleteRaptorResults, downloadRaptorArtifact, listAlterations } from "@/services/dataset-artifact-service";
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
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [deleted, setDeleted] = useState<{ deletedCount: number; artifactCount: number } | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const key = ["ws", dataset.tenantId, "dataset-jobs", dataset.id];
  const historyKey = ["ws", dataset.tenantId, "dataset-alterations", dataset.id, historyPage];
  const jobs = useQuery({ queryKey: key, queryFn: ({ signal }) => listDatasetJobs(dataset.id, signal),
    enabled: current && open, retry: false, refetchInterval: query => query.state.data?.some(job => job.status === "running") ? 2000 : false });
  const history = useQuery({ queryKey: historyKey, queryFn: ({ signal }) => listAlterations(dataset.id, historyPage, signal),
    enabled: current && historyOpen, retry: false });
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

  async function deleteSummaries() {
    if (busy || !canManage || useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
    setBusy(true); setError(false); setDeleted(null);
    try {
      const result = await deleteRaptorResults(dataset.id);
      if (useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
      setDeleted(result); setDeleteOpen(false);
      await Promise.all([client.invalidateQueries({ queryKey: key }), client.invalidateQueries({ queryKey: historyKey.slice(0, 4) })]);
    } catch { setError(true); }
    finally { if (useWorkspaceStore.getState().activeTenantId === dataset.tenantId) setBusy(false); }
  }

  async function download(filename: string) {
    if (downloading || useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
    setDownloading(filename); setError(false);
    try {
      const blob = await downloadRaptorArtifact(filename);
      if (useWorkspaceStore.getState().activeTenantId !== dataset.tenantId) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = filename;
      document.body.append(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError(true); }
    finally { if (useWorkspaceStore.getState().activeTenantId === dataset.tenantId) setDownloading(null); }
  }

  return <section className="grid gap-4 rounded-lg border bg-card p-4" data-testid="dataset-derived-jobs">
    <Button type="button" variant="ghost" className="justify-start" data-testid="dataset-jobs-open" aria-expanded={open} onClick={() => setOpen(value => !value)}>{t("datasets.jobs.title")}</Button>
    {open ? <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">{t("datasets.jobs.help")}</p>
      {canManage ? <div className="flex flex-wrap gap-2"><Button type="button" data-testid="dataset-jobs-start" disabled={busy || jobs.data?.some(job => job.status === "running")} onClick={() => void start()}>{t("datasets.jobs.start")}</Button><Button type="button" variant="outline" data-testid="dataset-raptor-start" disabled={busy || jobs.data?.some(job => job.status === "running")} onClick={() => void startRaptor()}>{t("datasets.jobs.raptorStart")}</Button></div> : null}
      <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" data-testid="dataset-alteration-open" onClick={() => { setHistoryPage(1); setHistoryOpen(true); }}>{t("datasets.jobs.history")}</Button>{canManage ? <Button type="button" variant="destructive" data-testid="dataset-raptor-delete" disabled={busy} onClick={() => { setHistoryOpen(false); setDeleteOpen(true); }}>{t("datasets.jobs.deleteRaptor")}</Button> : null}</div>
      {jobs.isPending ? <p role="status">{t("datasets.jobs.loading")}</p> : null}
      {jobs.isError ? <Alert role="alert">{t("datasets.jobs.failed")} <Button type="button" variant="outline" onClick={() => void jobs.refetch()}>{t("datasets.jobs.retry")}</Button></Alert> : null}
      {jobs.data?.length === 0 ? <p>{t("datasets.jobs.empty")}</p> : null}
      {jobs.data?.map(job => <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3" data-testid="dataset-job-row">
        <div><p className="text-sm font-medium">{t(job.type === "raptor" ? "datasets.jobs.raptor" : "datasets.jobs.enrich")}</p><p className="text-xs text-muted-foreground" data-testid="dataset-job-progress">{t(`datasets.jobs.status.${job.status}`)} · {t(job.type === "raptor" ? "datasets.jobs.countsRaptor" : "datasets.jobs.counts", { completed: job.completed, total: job.total, failed: job.failed })}</p></div>
        <div className="flex gap-2">{job.status === "done" && job.artifactFilename ? <Button type="button" variant="outline" data-testid="dataset-job-artifact" disabled={downloading === job.artifactFilename} onClick={() => void download(job.artifactFilename!)}>{t("datasets.jobs.download")}</Button> : null}
          {canManage && job.status === "running" ? <Button type="button" variant="outline" disabled={busy} onClick={() => setCancelId(job.id)}>{t("datasets.jobs.cancel")}</Button> : null}</div>
      </div>)}
      {deleted ? <p role="status" data-testid="dataset-raptor-deleted">{t("datasets.jobs.deleted", { count: deleted.deletedCount, artifacts: deleted.artifactCount })}</p> : null}
      {error ? <Alert role="alert">{t("datasets.jobs.failed")}</Alert> : null}
    </div> : null}
    <AlertDialog open={cancelId !== null} onOpenChange={value => { if (!value && !busy) setCancelId(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t(jobs.data?.find(job => job.id === cancelId)?.type === "raptor" ? "datasets.jobs.cancelRaptorTitle" : "datasets.jobs.cancelTitle")}</AlertDialogTitle><AlertDialogDescription>{t(jobs.data?.find(job => job.id === cancelId)?.type === "raptor" ? "datasets.jobs.cancelRaptorHelp" : "datasets.jobs.cancelHelp")}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("datasets.jobs.keep")}</AlertDialogCancel><AlertDialogAction asChild><Button type="button" disabled={busy} onClick={event => { event.preventDefault(); void cancel(); }}>{t("datasets.jobs.cancel")}</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    <AlertDialog open={deleteOpen} onOpenChange={value => { if (!busy) setDeleteOpen(value); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("datasets.jobs.deleteTitle")}</AlertDialogTitle><AlertDialogDescription>{t("datasets.jobs.deleteHelp", { name: dataset.name })}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("datasets.jobs.keepSummaries")}</AlertDialogCancel><AlertDialogAction asChild><Button type="button" variant="destructive" disabled={busy} onClick={event => { event.preventDefault(); void deleteSummaries(); }}>{t("datasets.jobs.deleteRaptor")}</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    <Sheet open={historyOpen} onOpenChange={setHistoryOpen}><SheetContent side="right" closeLabel={t("source.close")} data-testid="dataset-alteration-history"><SheetHeader><SheetTitle>{t("datasets.jobs.history")}</SheetTitle><SheetDescription>{t("datasets.jobs.historyHelp")}</SheetDescription></SheetHeader><div className="min-h-0 flex-1 overflow-y-auto">{history.isPending ? <p role="status">{t("datasets.jobs.loading")}</p> : null}{history.isError ? <Alert role="alert">{t("datasets.jobs.failed")}</Alert> : null}{history.data?.items.length === 0 ? <p>{t("datasets.jobs.historyEmpty")}</p> : null}<ol className="grid gap-2">{history.data?.items.map((item, index) => <li key={`${item.generation}:${item.time}:${index}`} className="rounded-md border p-3" data-testid="dataset-alteration-row"><p>{t("datasets.jobs.historyRow", { count: item.deletedCount, status: item.outcome })}</p><p className="text-xs text-muted-foreground">{new Date(item.time).toLocaleString()} · {item.actor}</p></li>)}</ol></div><div className="flex justify-between gap-2 border-t pt-3"><Button type="button" variant="outline" disabled={historyPage <= 1} onClick={() => setHistoryPage(page => page - 1)}>{t("datasets.jobs.previous")}</Button><Button type="button" variant="outline" disabled={!history.data || historyPage * history.data.size >= history.data.total} onClick={() => setHistoryPage(page => page + 1)}>{t("datasets.jobs.next")}</Button></div></SheetContent></Sheet>
  </section>;
}
