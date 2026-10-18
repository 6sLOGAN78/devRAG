import { ChevronLeft } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { ErrorState } from "@/components/error-state";
import { PagePreview, type PreviewSelection } from "@/components/document-preview/page-preview";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { METHOD_STEMS, isChunkMethod } from "@/constants/chunk-methods";
import { datasetFilesPath, documentViewerPath } from "@/constants/app-paths";
import { useChunkRefresh, useChunksRequest, type ChunkShow } from "@/hooks/use-chunk-request";
import { useCanChangeDocument } from "@/hooks/use-dataset-permissions";
import { useDatasetBinding } from "@/hooks/use-dataset-binding";
import { documentDetailKey, useDocumentDetailRequest } from "@/hooks/use-document-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { ChunkView } from "@/services/chunk-service";
import type { DatasetDetailView } from "@/services/dataset-service";
import type { DocumentDetailView } from "@/services/document-service";
import { StatusKindBadge, statusKindOf } from "../dataset/document-status-badge";
import { datasetPageState } from "../dataset/errors";
import { useParseActions } from "../dataset/parse-actions";
import { ParsingDetailsSheet } from "../dataset/parsing-details-sheet";
import { ReparseDialog } from "../dataset/reparse-dialog";
import { CHUNKS_PAGE_SIZE } from "@/hooks/use-chunk-request";
import { DiscardChangesDialog } from "./discard-dialog";
import { ChunkList, MAX_KEYWORDS, type Editing } from "./chunk-list";
import { useEditGuard } from "./use-edit-guard";
import { ChunkNotices } from "./chunk-notices";
import { ChunkListSkeleton, DocumentEmpty, InspectorNotFound, NoPreviewNote, typeLabelOf } from "./inspector-states";

const HEX_ID = /^[0-9a-f]{32}$/;
/** An absurd `page` in the address is capped here; the list steps back when the server answers an empty page. */
const MAX_PAGE = 100000;

/** `page` from the address: a whole number of at least 1, otherwise 1. */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return 1;
  return Math.min(MAX_PAGE, Math.max(1, Number(raw)));
}

/** `show` from the address: `on` or `off`, anything else is `all`. */
function parseShow(raw: string | null): ChunkShow {
  return raw === "on" || raw === "off" ? raw : "all";
}

interface Selected {
  chunk: ChunkView;
  number: number;
  pageSizes: Record<string, [number, number]>;
}

function InspectorSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="chunk-page-skeleton" className="flex flex-col gap-6">
      <p role="status" className="sr-only">
        {t("inspector.loading")}
      </p>
      <Skeleton className="h-8 w-64" aria-hidden="true" />
      <Skeleton className="h-4 w-80" aria-hidden="true" />
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-2">
        <Skeleton data-testid="preview-skeleton-pane" className="h-[40vh] min-h-[240px] w-full" aria-hidden="true" />
        <ChunkListSkeleton />
      </div>
    </div>
  );
}

interface BodyProps {
  dataset: DatasetDetailView;
  doc: DocumentDetailView;
  page: number;
  keywords: string;
  show: ChunkShow;
  setPage: (page: number, options?: { replace?: boolean }) => void;
  setKeywords: (keywords: string) => void;
  setShow: (show: ChunkShow) => void;
  clearFilters: () => void;
  /** After an add: no search, no filter, this page. */
  showPage: (page: number) => void;
}

/** The inspector once the dataset is bound and the document is known. Keyed by document, so the selection never carries over. */
function InspectorBody({ dataset, doc, page, keywords, show, setPage, setKeywords, setShow, clearFilters, showPage }: BodyProps) {
  const { t, i18n } = useTranslation();
  const canChange = useCanChangeDocument(dataset, doc);
  const parsing = doc.run === "1";
  const actions = useParseActions(dataset.id);
  const chunks = useChunksRequest({ datasetId: dataset.id, docId: doc.id, page, keywords, show });
  useChunkRefresh(doc);

  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const [editing, setEditing] = useState<Editing | null>(null);
  const [dirty, setDirty] = useState(false);
  const [newId, setNewId] = useState<string | null>(null);
  const edit = useEditGuard(dirty);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [sheetOpen, setSheetOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const titleRef = useRef<HTMLHeadingElement | null>(null);

  const pages = doc.pagesTotal ?? 0;
  const hasPreview = doc.preview === "pages" && pages >= 1;
  const kind = statusKindOf(doc);
  const methodLabel = isChunkMethod(doc.parserId) ? t(`datasets.chunking.method.${METHOD_STEMS[doc.parserId]}.title`) : doc.parserId;

  useEffect(() => {
    document.title = t("inspector.documentTitle", { name: doc.name });
  }, [doc.name, t, i18n.language]);

  const select = useCallback((chunk: ChunkView, number: number, pageSizes: Record<string, [number, number]>, chipPage?: number) => {
    setSelected({ chunk, number, pageSizes });
    const first = chipPage ?? chunk.positions[0]?.page;
    if (first !== undefined) setPreviewPage(first);
  }, []);

  const selection: PreviewSelection | null = selected === null ? null : { chunkId: selected.chunk.id, number: selected.number, positions: selected.chunk.positions };

  function openDetails(button: HTMLElement): void {
    opener.current = button;
    setSheetOpen(true);
  }

  function restoreFocus(event: Event): void {
    event.preventDefault();
    if (opener.current?.isConnected === true) opener.current.focus();
    else titleRef.current?.focus();
  }

  /** Leaving the list as it is (another page, search or filter) closes the editor, after asking when its text is changed. */
  const leave = (action: () => void) =>
    edit.guard(() => {
      setEditing(null);
      action();
    });

  function added(chunk: ChunkView): void {
    edit.release();
    setEditing(null);
    setNewId(chunk.id);
    // The write refreshed the document before it answered, so its count already includes the new chunk, which is the last one.
    const count = queryClient.getQueryData<DocumentDetailView>(documentDetailKey(tenantId, dataset.id, doc.id))?.chunkCount ?? doc.chunkCount;
    showPage(Math.max(1, Math.ceil(count / CHUNKS_PAGE_SIZE)));
  }

  function saved(chunk: ChunkView): void {
    if (editing?.kind === "add") added(chunk);
    else {
      edit.release();
      setEditing(null);
    }
  }

  const noChunks = chunks.data !== undefined && chunks.data.total === 0 && keywords === "" && show === "all";
  const listBody = noChunks && editing?.kind !== "add" ? (
    <DocumentEmpty
      document={doc}
      canChange={canChange}
      busy={actions.isBusy(doc.id)}
      onParse={() => void actions.parse([doc.id])}
      onCancel={() => void actions.cancel([doc.id])}
      onDetails={openDetails}
      onAddByHand={canChange ? () => setEditing({ kind: "add" }) : undefined}
    />
  ) : (
    <ChunkList
      query={chunks}
      datasetId={dataset.id}
      docId={doc.id}
      page={page}
      keywords={keywords}
      show={show}
      canChange={canChange && !parsing}
      showPages={hasPreview}
      selectedId={selected?.chunk.id ?? null}
      onPage={(next, options) => (options?.replace === true ? setPage(next, options) : leave(() => setPage(next, options)))}
      onSearch={(next) => leave(() => setKeywords(next))}
      onShow={(next) => leave(() => setShow(next))}
      onClear={() => leave(clearFilters)}
      onSelect={select}
      editing={editing}
      guard={edit.guard}
      onEdit={(chunk, number) => setEditing({ kind: "edit", chunk, number })}
      onAdd={() => setEditing({ kind: "add" })}
      onEditorDirty={setDirty}
      onEditorClose={() => setEditing(null)}
      onEditorSaved={saved}
      textareaRef={textarea}
      newId={newId}
      onNewShown={() => setNewId(null)}
    />
  );

  return (
    <div data-testid="chunk-page" className="flex flex-col gap-6">
      <Link
        to={datasetFilesPath(dataset.id)}
        data-testid="chunk-back"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        <span className="break-all">{dataset.name}</span>
      </Link>
      <PageHeader title={doc.name} titleHint={doc.name} titleClassName="line-clamp-2 break-all" titleRef={titleRef} />
      <div data-testid="chunk-meta" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-normal text-muted-foreground">
        <StatusKindBadge kind={kind} />
        <span>{t("dataset.meta.chunks", { count: doc.chunkCount })}</span>
        <span>{t("inspector.meta.method", { method: methodLabel })}</span>
        <Link
          to={documentViewerPath(dataset.id, doc.id)}
          data-testid="chunk-open-document"
          className="rounded-sm text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t("inspector.meta.open")}
        </Link>
      </div>
      <ChunkNotices
        readOnly={!canChange}
        documentOff={!doc.enabled}
        parsing={parsing}
        partial={kind === "partial"}
        canOpenDetails={doc.lastLogId !== null}
        onDetails={openDetails}
      />
      {hasPreview ? (
        <div className="flex flex-col gap-6 lg:grid lg:grid-cols-2 lg:items-start">
          <div className="sticky top-14 z-10 h-[40vh] min-h-[240px] lg:top-20 lg:h-auto lg:max-h-[calc(100vh-7rem)]">
            <PagePreview
              datasetId={dataset.id}
              docId={doc.id}
              name={doc.name}
              pages={pages}
              page={previewPage}
              onPageChange={setPreviewPage}
              selection={selection}
              pageSizes={selected?.pageSizes}
              className="h-full lg:max-h-[calc(100vh-7rem)]"
            />
          </div>
          <div data-testid="chunk-list-column" className="min-w-0">
            {listBody}
          </div>
        </div>
      ) : (
        <div data-testid="chunk-list-column" className="flex max-w-3xl flex-col gap-4">
          <NoPreviewNote type={typeLabelOf(doc.suffix)} />
          {listBody}
        </div>
      )}
      <ParsingDetailsSheet
        datasetId={dataset.id}
        logId={doc.lastLogId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onCloseAutoFocus={restoreFocus}
        canParseAgain={() => canChange}
        onParseAgain={(id) => void actions.parse([id])}
      />
      <DiscardChangesDialog
        open={edit.pending}
        onKeep={edit.cancel}
        onDiscard={edit.confirm}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (textarea.current?.isConnected === true) textarea.current.focus();
        }}
      />
      <ReparseDialog confirm={actions.confirm} onReplace={actions.replace} onDismiss={actions.dismiss} onCloseAutoFocus={restoreFocus} />
    </div>
  );
}

/**
 * The chunk inspector (UI-16) at `/chunk?id=&doc=`: a document's chunks beside its original pages. It binds the workspace
 * like the dataset page and sends no request before it is bound (FE-02). `page`, `keywords` and `show` live in the
 * address; the selected chunk and the previewed page are local state (D-12).
 */
export default function ChunkInspectorPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const rawId = params.get("id") ?? "";
  const rawDoc = params.get("doc") ?? "";
  const valid = HEX_ID.test(rawId) && HEX_ID.test(rawDoc);
  const page = parsePage(params.get("page"));
  const keywords = (params.get("keywords") ?? "").slice(0, MAX_KEYWORDS);
  const show = parseShow(params.get("show"));

  const binding = useDatasetBinding({ datasetId: valid ? rawId : "" });
  const { dataset, bound } = binding;
  const detail = useDocumentDetailRequest(dataset?.id, rawDoc, bound && valid);
  const doc = detail.data;

  useEffect(() => {
    if (doc === undefined) document.title = t("inspector.documentTitleFallback");
  }, [doc, t, i18n.language]);

  const update = useCallback(
    (change: (next: URLSearchParams) => void, replace: boolean) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          change(next);
          return next;
        },
        { replace },
      );
    },
    [setParams],
  );
  const setPage = useCallback(
    (next: number, options?: { replace?: boolean }) => update((p) => (next <= 1 ? p.delete("page") : p.set("page", String(next))), options?.replace === true),
    [update],
  );
  const setKeywords = useCallback(
    (next: string) =>
      update((p) => {
        if (next === "") p.delete("keywords");
        else p.set("keywords", next.slice(0, MAX_KEYWORDS));
        p.delete("page");
      }, true),
    [update],
  );
  const setShow = useCallback(
    (next: ChunkShow) =>
      update((p) => {
        if (next === "all") p.delete("show");
        else p.set("show", next);
        p.delete("page");
      }, true),
    [update],
  );
  const showPage = useCallback(
    (next: number) =>
      update((p) => {
        p.delete("keywords");
        p.delete("show");
        if (next <= 1) p.delete("page");
        else p.set("page", String(next));
      }, false),
    [update],
  );
  const clearFilters = useCallback(
    () =>
      update((p) => {
        p.delete("keywords");
        p.delete("show");
        p.delete("page");
      }, false),
    [update],
  );

  if (!valid || binding.state === "not-found" || binding.unbindable) return <InspectorNotFound />;
  if (dataset === undefined) {
    if (binding.state === "error") return <ErrorState level="h1" heading={t("inspector.error.pageHeading")} onAction={binding.refetch} />;
    return <InspectorSkeleton />;
  }
  if (doc === undefined) {
    if (detail.isError) {
      if (datasetPageState(detail.error) === "notFound") return <InspectorNotFound />;
      return <ErrorState level="h1" heading={t("inspector.error.pageHeading")} onAction={() => void detail.refetch()} />;
    }
    return <InspectorSkeleton />;
  }
  return (
    <InspectorBody
      key={`${dataset.id}:${doc.id}`}
      dataset={dataset}
      doc={doc}
      page={page}
      keywords={keywords}
      show={show}
      setPage={setPage}
      setKeywords={setKeywords}
      setShow={setShow}
      clearFilters={clearFilters}
      showPage={showPage}
    />
  );
}
