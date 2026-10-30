import { ChevronLeft, Lock, SearchCheck, Upload, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { ChunkMethodDialog } from "@/components/chunk-method-dialog";
import { SETTINGS_MODES } from "@/constants/failure-codes";
import { DatasetActionsMenu } from "@/components/dataset-actions-menu";
import { DatasetSettingsDialog } from "@/components/dataset-settings-dialog";
import { DeleteDatasetDialog } from "@/components/delete-dataset-dialog";
import { FileUploadDialog } from "@/components/file-upload-dialog";
import { carriesFiles, readDropped } from "@/components/file-upload-dialog/dropzone";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DATASETS_PATH, retrievalTestPath } from "@/constants/app-paths";
import { useCanManageDataset } from "@/hooks/use-dataset-permissions";
import type { DatasetDetailView } from "@/services/dataset-service";
import { MAX_DOCUMENT_KEYWORDS_LENGTH } from "@/services/document-service";
import { DatasetTags } from "./tags";
import { DatasetFiles } from "./dataset-files";
import { DatasetPageSkeleton } from "./page-states";

/** An absurd `page` in the URL is capped here; the server answers an empty page and the table steps back. */
const MAX_PAGE = 100000;

/** `page` from the URL: a whole number of at least 1, otherwise 1. */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return 1;
  return Math.min(MAX_PAGE, Math.max(1, Number(raw)));
}

/** `keywords` from the URL, cut to the length the API accepts before any request is built. */
function parseKeywords(raw: string | null): string {
  return (raw ?? "").slice(0, MAX_DOCUMENT_KEYWORDS_LENGTH);
}

interface DatasetWorkspaceProps {
  dataset: DatasetDetailView;
  /** False while the page is still switching to the dataset's workspace: the table waits so it asks under the right key. */
  ready: boolean;
  /** The dataset is gone (the delete dialog succeeded): the page leaves. */
  onDeleted: () => void;
  /** The delete dialog opens or closes: the page stops watching the detail while it is open (the dialog loads its own). */
  onDeleteDialogChange: (open: boolean) => void;
}

/**
 * The open dataset (UI-11, UI-12): back link, name and actions, meta line, description and the document table, with the
 * dialogs of plans 03-24 and 03-25 and a page-level drop target. Controls the caller may not use are absent: the actions
 * menu is for the creator, owner and admins; Upload files is for every member who can see the dataset (D-09).
 */
export function DatasetWorkspace({ dataset, ready, onDeleted, onDeleteDialogChange }: DatasetWorkspaceProps) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const page = parsePage(params.get("page"));
  const keywords = parseKeywords(params.get("keywords"));
  const canManage = useCanManageDataset(dataset);

  const [dialog, setDialog] = useState<"settings" | "chunking" | "delete" | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [dropped, setDropped] = useState<File[] | undefined>(undefined);
  const [dragging, setDragging] = useState(false);
  const [documentsEmpty, setDocumentsEmpty] = useState(false);
  const depth = useRef(0);
  const deleted = useRef(false);
  const menuButton = useRef<HTMLButtonElement | null>(null);
  const uploadOpener = useRef<HTMLElement | null>(null);
  const pageRoot = useRef<HTMLDivElement | null>(null);
  const title = useRef<HTMLHeadingElement | null>(null);
  const modalOpen = uploadOpen || dialog !== null;

  const setPage = useCallback(
    (next: number, options?: { replace?: boolean }) => {
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next <= 1) updated.delete("page");
          else updated.set("page", String(next));
          return updated;
        },
        { replace: options?.replace === true },
      );
    },
    [setParams],
  );

  const search = useCallback(
    (next: string) => {
      setParams((current) => {
        const updated = new URLSearchParams(current);
        updated.delete("page");
        if (next === "") updated.delete("keywords");
        else updated.set("keywords", next.slice(0, MAX_DOCUMENT_KEYWORDS_LENGTH));
        return updated;
      });
    },
    [setParams],
  );

  // A file dropped outside the target must not make the browser open it and leave the app (T-03-31-05).
  useEffect(() => {
    const guard = (event: globalThis.DragEvent) => {
      if (carriesFiles(event.dataTransfer)) event.preventDefault();
    };
    window.addEventListener("dragover", guard);
    window.addEventListener("drop", guard);
    return () => {
      window.removeEventListener("dragover", guard);
      window.removeEventListener("drop", guard);
    };
  }, []);

  // A drag that ends outside the page (Esc, or dropped elsewhere) sends no dragleave for every dragenter: reset the overlay.
  useEffect(() => {
    if (!dragging) return;
    const reset = () => {
      depth.current = 0;
      setDragging(false);
    };
    window.addEventListener("dragend", reset);
    window.addEventListener("drop", reset);
    return () => {
      window.removeEventListener("dragend", reset);
      window.removeEventListener("drop", reset);
    };
  }, [dragging]);

  function openUpload(event?: { currentTarget: HTMLElement }): void {
    uploadOpener.current = event?.currentTarget ?? null;
    setDropped(undefined);
    setUploadOpen(true);
  }

  function onUploadOpenChange(open: boolean): void {
    setUploadOpen(open);
    // `initialFiles` is read once at opening: forget the drop, or the next opening would queue it again.
    if (!open) setDropped(undefined);
  }

  /** Back to the control that opened the dialog; for a drop, or when that control is gone, the header button, then the title. */
  function restoreUploadFocus(event: Event): void {
    event.preventDefault();
    const opener = uploadOpener.current?.isConnected === true ? uploadOpener.current : null;
    const header = pageRoot.current?.querySelector<HTMLElement>('[data-testid="dataset-upload"]') ?? null;
    (opener ?? header ?? title.current)?.focus();
  }

  function dialogOpenChange(kind: "settings" | "chunking" | "delete", open: boolean): void {
    setDialog(open ? kind : null);
    if (kind === "delete") onDeleteDialogChange(open);
  }

  function returnToMenu(event: Event): void {
    event.preventDefault();
    if (!deleted.current) menuButton.current?.focus();
  }

  function onDragEnter(event: DragEvent<HTMLDivElement>): void {
    if (modalOpen || !carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    depth.current += 1;
    setDragging(true);
  }

  function onDragOver(event: DragEvent<HTMLDivElement>): void {
    if (modalOpen || !carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>): void {
    if (modalOpen || !carriesFiles(event.dataTransfer)) return;
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setDragging(false);
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    if (modalOpen || !carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    // Folders cannot be told apart once converted to files: only real files are queued.
    const files = readDropped(event.dataTransfer)
      .filter((entry) => !entry.isDirectory)
      .map((entry) => entry.file);
    uploadOpener.current = null;
    setDropped(files);
    setUploadOpen(true);
  }

  const shared = dataset.permission === "team";
  const VisibilityIcon = shared ? Users : Lock;
  const uploadButton = documentsEmpty ? undefined : (
    <Button type="button" data-testid="dataset-upload" onClick={(event) => openUpload(event)}>
      <Upload aria-hidden="true" />
      {t("dataset.upload")}
    </Button>
  );
  const actions = (
    <>
      {canManage ? (
        <DatasetActionsMenu
          name={dataset.name}
          triggerRef={menuButton}
          onSettings={() => dialogOpenChange("settings", true)}
          onChunking={() => dialogOpenChange("chunking", true)}
          onDelete={() => dialogOpenChange("delete", true)}
        />
      ) : null}
      <Button variant="outline" asChild><Link data-testid="dataset-test-retrieval" to={retrievalTestPath(dataset.id)}><SearchCheck aria-hidden="true" />{t("retrieval.entry")}</Link></Button>
      {uploadButton}
    </>
  );

  return (
    <div
      ref={pageRoot}
      data-testid="dataset-page"
      className="relative flex min-h-[60vh] flex-col gap-6"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <Link
        to={DATASETS_PATH}
        data-testid="dataset-back"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        {t("dataset.back")}
      </Link>
      <PageHeader title={dataset.name} titleRef={title} actions={canManage || uploadButton !== undefined ? actions : undefined} />
      <div className="flex flex-col gap-2">
        <div data-testid="dataset-meta" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-normal text-muted-foreground">
          <Badge variant="outline">
            <VisibilityIcon className="size-3" aria-hidden="true" />
            {shared ? t("datasets.visibility.team") : t("datasets.visibility.me")}
          </Badge>
          <span className="tabular-nums">{t("datasets.card.documents", { count: dataset.docNum })}</span>
          <span className="tabular-nums">{t("dataset.meta.chunks", { count: dataset.chunkNum })}</span>
          {dataset.embdId === "" ? null : (
            <span className="flex items-center gap-1">
              <span>{t("dataset.meta.embedding")}</span>
              <span className="break-all font-mono">{dataset.embdId}</span>
            </span>
          )}
        </div>
        {dataset.description === "" ? null : <p className="max-w-prose break-words text-sm font-normal text-muted-foreground">{dataset.description}</p>}
      </div>
      {ready ? (
        <DatasetFiles
          dataset={dataset}
          limits={dataset.uploadLimits}
          page={page}
          keywords={keywords}
          onPageChange={setPage}
          onSearch={search}
          onUpload={() => openUpload()}
          onEmptyChange={setDocumentsEmpty}
        />
      ) : (
        <DatasetPageSkeleton />
      )}
      {ready ? <DatasetTags key={`${dataset.tenantId}:${dataset.id}`} dataset={dataset}/> : null}
      {dragging ? (
        <div
          data-testid="dataset-drop-overlay"
          className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-lg border-2 border-primary bg-background/80 p-6 text-center text-xl font-semibold"
        >
          <span className="break-words">{t("dataset.dropOverlay", { name: dataset.name })}</span>
        </div>
      ) : null}
      <FileUploadDialog
        dataset={{ id: dataset.id, name: dataset.name, docNum: dataset.docNum }}
        limits={dataset.uploadLimits}
        open={uploadOpen}
        onOpenChange={onUploadOpenChange}
        initialFiles={dropped}
        onCloseAutoFocus={restoreUploadFocus}
      />
      {canManage ? (
        <>
          <DatasetSettingsDialog dataset={dataset} open={dialog === "settings"} onOpenChange={(open) => dialogOpenChange("settings", open)} onCloseAutoFocus={returnToMenu} />
          <ChunkMethodDialog
            target={{ mode: SETTINGS_MODES.dataset, datasetId: dataset.id, tenantId: dataset.tenantId, name: dataset.name }}
            open={dialog === "chunking"}
            onOpenChange={(open) => dialogOpenChange("chunking", open)}
            onCloseAutoFocus={returnToMenu}
          />
          <DeleteDatasetDialog
            dataset={{ id: dataset.id, name: dataset.name, tenantId: dataset.tenantId }}
            open={dialog === "delete"}
            onOpenChange={(open) => dialogOpenChange("delete", open)}
            onSuccess={() => {
              deleted.current = true;
              onDeleted();
            }}
            onCloseAutoFocus={returnToMenu}
          />
        </>
      ) : null}
    </div>
  );
}
