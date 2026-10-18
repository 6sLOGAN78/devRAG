import { FileUp, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatBytes, resolveUploadLimits } from "@/components/file-upload-dialog/file-rules";
import { ChunkMethodDialog, type ChunkTarget } from "@/components/chunk-method-dialog";
import { SETTINGS_MODES } from "@/constants/failure-codes";
import { DeleteDocumentDialog } from "@/components/delete-document-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { canChangeDocument, useRoleIn } from "@/hooks/use-dataset-permissions";
import { DOCUMENTS_PAGE_SIZE, useDocumentsRequest, useInvalidateOnParseEnd, usePollHealth } from "@/hooks/use-document-request";
import { useUserStore } from "@/stores/user-store";
import type { UploadLimitsView } from "@/services/dataset-service";
import { MAX_DOCUMENT_KEYWORDS_LENGTH, type DocumentView } from "@/services/document-service";
import type { IngestionLogDetail } from "@/services/ingestion-service";
import { DocumentRow } from "./document-row";
import { IngestionSummary } from "./ingestion-summary";
import { useParseActions, useParseAnnouncements } from "./parse-actions";
import { ParsingDetailsSheet } from "./parsing-details-sheet";
import { ReparseDialog } from "./reparse-dialog";
import { SelectionBar } from "./selection-bar";

const SKELETON_ROWS = 5;
const COLUMNS = ["name", "size", "uploaded", "status", "progress", "inSearch", "actions"] as const;

export interface DatasetFilesProps {
  dataset: { id: string; name: string; createdBy: string; tenantId: string };
  /** `uploadLimits` of the dataset detail: the empty state names the per-file size. */
  limits: UploadLimitsView | null;
  /** Current page (1-based) and search, both owned by the caller (the URL). */
  page: number;
  keywords: string;
  /** `replace` is true when the table steps back by itself (the page emptied), so Back does not return to an empty page. */
  onPageChange: (page: number, options?: { replace?: boolean }) => void;
  onSearch: (keywords: string) => void;
  /** The empty state's "Upload files" action. */
  onUpload: () => void;
  /** Called when the empty state starts or stops showing, so the page can hide its own header action. */
  onEmptyChange?: (empty: boolean) => void;
}

function TableSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="documents-skeleton" className="flex flex-col">
      <p role="status" className="sr-only">
        {t("datasets.files.loading")}
      </p>
      <Skeleton className="h-10 w-full rounded-none" aria-hidden="true" />
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} data-testid="document-row-skeleton" className="h-12 w-full rounded-none border-b border-background" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * The document table of a dataset (UI-11, DOC-08): search, 20 a page, status badge, progress and a delete icon on the
 * rows the caller may delete. It owns its documents query and the delete confirmation. After a delete, focus goes to
 * the table caption (the row is gone) and a page that became empty steps back to the last page that exists. Names are
 * user text and render as text nodes only.
 */
export function DatasetFiles({ dataset, limits, page, keywords, onPageChange, onSearch, onUpload, onEmptyChange }: DatasetFilesProps) {
  const { t, i18n } = useTranslation();
  const documents = useDocumentsRequest({ datasetId: dataset.id, page, keywords });
  const { pollPaused } = usePollHealth(documents);
  useInvalidateOnParseEnd(dataset.id, documents.data?.items);
  const announcement = useParseAnnouncements(documents.data?.items);
  const actions = useParseActions(dataset.id);
  const userId = useUserStore((state) => state.user?.id ?? null);
  const role = useRoleIn(dataset.tenantId);
  const items = documents.data?.items ?? [];
  const total = documents.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / DOCUMENTS_PAGE_SIZE));
  const pastEnd = documents.data !== undefined && items.length === 0 && total > 0 && page > pages;
  const searching = keywords !== "";
  const empty = documents.data !== undefined && !pastEnd && items.length === 0 && !searching;

  const caption = useRef<HTMLTableCaptionElement | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const deleted = useRef(false);
  const [target, setTarget] = useState<DocumentView | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [focusCaption, setFocusCaption] = useState(false);
  const [seenDocuments, setSeenDocuments] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const reparseIds = useRef<string[]>([]);
  // The details sheet keeps its entry after closing so it can slide out with its content; the body mounts only while open.
  const detailsOpener = useRef<HTMLElement | null>(null);
  const [detailsLogId, setDetailsLogId] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  // The chunking dialog keeps its target after closing so it can fade out; its body mounts only while open (FE-04).
  const chunkingOpener = useRef<HTMLElement | null>(null);
  const [chunkingTarget, setChunkingTarget] = useState<ChunkTarget | null>(null);
  const [chunkingOpen, setChunkingOpen] = useState(false);

  // A row the caller may select: they may change it and it can be parsed or is parsing. The same rule the row draws.
  const qualifies = (document: DocumentView): boolean => canChangeDocument(dataset.createdBy, document.createdBy, userId, role) && (document.parseable || document.run === "1");
  const qualifying = items.filter(qualifies);
  const selectedItems = items.filter((document) => selected.has(document.id));
  const parseIds = selectedItems.filter((document) => document.run !== "1").map((document) => document.id);
  const cancelIds = selectedItems.filter((document) => document.run === "1").map((document) => document.id);

  // Selection is per page: a page change, a search change or another workspace's dataset starts it over.
  useEffect(() => {
    setSelected((current) => (current.size === 0 ? current : new Set()));
  }, [page, keywords, dataset.id]);

  // A row that disappeared from the page (deleted elsewhere) is dropped from the selection; a polled refetch keeps the rest.
  useEffect(() => {
    if (documents.data === undefined) return;
    const present = new Set(documents.data.items.map((document) => document.id));
    setSelected((current) => {
      const kept = [...current].filter((id) => present.has(id));
      return kept.length === current.size ? current : new Set(kept);
    });
  }, [documents.data]);

  useEffect(() => {
    if (actions.confirm !== null) reparseIds.current = actions.confirm.ids;
  }, [actions.confirm]);

  const onEmptyChangeRef = useRef(onEmptyChange);
  onEmptyChangeRef.current = onEmptyChange;
  useEffect(() => {
    if (documents.data !== undefined) onEmptyChangeRef.current?.(empty);
  }, [documents.data, empty]);

  useEffect(() => {
    if (items.length > 0) setSeenDocuments(true);
  }, [items.length]);

  // After the last page empties (a delete, or a delete elsewhere) step back to the last page that exists.
  useEffect(() => {
    if (pastEnd) onPageChange(pages, { replace: true });
  }, [pastEnd, pages, onPageChange]);

  // After a delete the row (and the dialog that had focus) is gone: focus the caption once the table is shown again.
  const tableShown = !documents.isPending && !pastEnd && items.length > 0;
  useEffect(() => {
    if (!focusCaption || !tableShown) return;
    const timer = window.setTimeout(() => {
      caption.current?.focus();
      setFocusCaption(false);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focusCaption, tableShown]);

  function askDelete(document: DocumentView, button: HTMLButtonElement): void {
    opener.current = button;
    deleted.current = false;
    setTarget(document);
    setConfirming(true);
  }

  /** Back to the row's delete icon when the confirmation was dismissed; after a delete the caption takes focus instead. */
  function restoreFocus(event: Event): void {
    event.preventDefault();
    if (!deleted.current && opener.current?.isConnected === true) opener.current.focus();
  }

  function showDetails(logId: string, button: HTMLElement): void {
    detailsOpener.current = button;
    setDetailsLogId(logId);
    setDetailsOpen(true);
  }

  /** Back to the link or menu button that opened the sheet; when the row is gone, the table caption. */
  function restoreDetailsFocus(event: Event): void {
    event.preventDefault();
    const target = detailsOpener.current?.isConnected === true ? detailsOpener.current : caption.current;
    target?.focus();
  }

  function openChunking(document: DocumentView, button: HTMLElement): void {
    chunkingOpener.current = button;
    setChunkingTarget({ mode: SETTINGS_MODES.document, datasetId: dataset.id, tenantId: dataset.tenantId, documentId: document.id, name: document.name });
    setChunkingOpen(true);
  }

  /** Back to the row's menu button; when the row is gone, the table caption. */
  function restoreChunkingFocus(event: Event): void {
    event.preventDefault();
    const target = chunkingOpener.current?.isConnected === true ? chunkingOpener.current : caption.current;
    target?.focus();
  }

  /** The caller may parse the entry's document again: it is the document's latest run, it ended badly, and they may change it. */
  function canParseAgain(log: IngestionLogDetail): boolean {
    const document = items.find((candidate) => candidate.id === log.documentId);
    if (document === undefined || document.lastLogId !== log.id || !document.parseable) return false;
    if (log.result !== "failed" && log.result !== "cancelled") return false;
    return canChangeDocument(dataset.createdBy, document.createdBy, userId, role);
  }

  /** After a bulk action the bar is gone with the focus on it: the caption takes it. */
  function afterBulk(): void {
    setSelected(new Set());
    setFocusCaption(true);
  }

  function toggleSelected(id: string, checked: boolean): void {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function toggleAll(checked: boolean): void {
    setSelected((current) => {
      const next = new Set(current);
      for (const document of qualifying) {
        if (checked) next.add(document.id);
        else next.delete(document.id);
      }
      return next;
    });
  }

  /** Back to the menu button of the row the dialog was about (the selection's first row for several); else the caption. */
  function restoreAfterReparse(event: Event): void {
    event.preventDefault();
    const table = caption.current?.closest("table");
    const id = reparseIds.current[0];
    const row = id === undefined ? null : Array.from(table?.querySelectorAll<HTMLElement>("[data-doc-id]") ?? []).find((element) => element.dataset.docId === id);
    const target = row?.querySelector<HTMLElement>('[data-testid="document-more"]') ?? caption.current;
    target?.focus();
  }

  const selectColumn = qualifying.length > 0;
  const allSelected = selectColumn && qualifying.every((document) => selected.has(document.id));
  const someSelected = qualifying.some((document) => selected.has(document.id));
  const showSummary = documents.data !== undefined && !empty;
  const showToolbar = items.length > 0 || searching || (documents.isPending && seenDocuments);
  const maxFile = formatBytes(resolveUploadLimits(limits).maxFileBytes, i18n.language);

  let body;
  if (documents.isPending || pastEnd) {
    body = <TableSkeleton />;
  } else if (documents.isError && documents.data === undefined) {
    body = (
      <div className="p-6">
        <ErrorState heading={t("datasets.files.error.heading")} onAction={() => void documents.refetch()} />
      </div>
    );
  } else if (items.length === 0 && searching) {
    body = (
      <EmptyState
        as="h2"
        icon={SearchX}
        heading={t("datasets.files.noMatch.heading", { keywords })}
        body={t("datasets.files.noMatch.body")}
        action={
          <Button type="button" variant="link" onClick={() => onSearch("")}>
            {t("common.search.clear")}
          </Button>
        }
      />
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState
        as="h2"
        icon={FileUp}
        heading={t("datasets.files.empty.heading")}
        body={t("datasets.files.empty.body", { size: maxFile })}
        action={
          <Button type="button" data-testid="dataset-upload" onClick={onUpload}>
            {t("dataset.upload")}
          </Button>
        }
      />
    );
  } else {
    body = (
      <Table data-testid="documents-table">
        <TableCaption ref={caption} tabIndex={-1} className="focus:outline-none">
          {t("datasets.files.caption", { name: dataset.name })}
        </TableCaption>
        <TableHeader>
          <TableRow className="h-10">
            {selectColumn ? (
              <TableHead className="w-12 px-2">
                <span className="sr-only">{t("datasets.files.col.select")}</span>
                <Checkbox checked={allSelected} indeterminate={someSelected && !allSelected} onChange={toggleAll} aria-label={t("datasets.files.selectAll")} data-testid="documents-select-all" />
              </TableHead>
            ) : null}
            {COLUMNS.map((column) => (
              <TableHead key={column} className={column === "actions" ? "text-right" : undefined}>
                {t(`datasets.files.col.${column}`)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((document) => (
            <DocumentRow
              key={document.id}
              dataset={dataset}
              document={document}
              actions={actions}
              selectColumn={selectColumn}
              selected={selected.has(document.id)}
              onSelect={(checked) => toggleSelected(document.id, checked)}
              onDelete={askDelete}
              onShowDetails={showDetails}
              onChunking={openChunking}
            />
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p role="status" data-testid="documents-live" className="sr-only">
        {announcement}
      </p>
      {showSummary ? <IngestionSummary datasetId={dataset.id} /> : null}
      {showToolbar ? (
        <div className="flex flex-wrap items-center gap-3">
          <div data-testid="documents-search" className="w-full max-w-sm">
            <SearchInput
              value={keywords}
              onSearch={(next) => onSearch(next.slice(0, MAX_DOCUMENT_KEYWORDS_LENGTH))}
              label={t("datasets.files.search")}
              clearLabel={t("common.search.clear")}
            />
          </div>
          {selectedItems.length > 0 ? (
            <SelectionBar
              count={selectedItems.length}
              parseCount={parseIds.length}
              cancelCount={cancelIds.length}
              busy={selectedItems.some((document) => actions.isBusy(document.id))}
              onParse={() => void actions.parse(parseIds, afterBulk)}
              onCancel={() => void actions.cancel(cancelIds, afterBulk)}
              onClear={() => setSelected(new Set())}
            />
          ) : null}
        </div>
      ) : null}
      {pollPaused && documents.data !== undefined ? (
        <Alert variant="info" data-testid="documents-poll-paused">
          <span className="flex flex-wrap items-center gap-2">
            {t("datasets.files.pollPaused")}
            <Button type="button" variant="ghost" size="sm" onClick={() => void documents.refetch()}>
              {t("errorState.action")}
            </Button>
          </span>
        </Alert>
      ) : null}
      <Card className="overflow-x-auto">{body}</Card>
      {!documents.isPending && !documents.isError && !pastEnd && items.length > 0 ? (
        <Pagination
          page={page}
          pages={pages}
          onPageChange={onPageChange}
          previousLabel={t("common.pagination.previous")}
          nextLabel={t("common.pagination.next")}
          statusLabel={t("common.pagination.status", { page, pages })}
        />
      ) : null}
      <ParsingDetailsSheet
        datasetId={dataset.id}
        logId={detailsLogId}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        onCloseAutoFocus={restoreDetailsFocus}
        canParseAgain={canParseAgain}
        onParseAgain={(documentId) => void actions.parse([documentId])}
      />
      <ChunkMethodDialog target={chunkingTarget} open={chunkingOpen} onOpenChange={setChunkingOpen} onCloseAutoFocus={restoreChunkingFocus} />
      <ReparseDialog confirm={actions.confirm} onReplace={actions.replace} onDismiss={actions.dismiss} onCloseAutoFocus={restoreAfterReparse} />
      {target === null ? null : (
        <DeleteDocumentDialog
          datasetId={dataset.id}
          datasetName={dataset.name}
          document={{ id: target.id, name: target.name }}
          open={confirming}
          onOpenChange={setConfirming}
          onSuccess={() => {
            deleted.current = true;
            setFocusCaption(true);
          }}
          onCloseAutoFocus={restoreFocus}
        />
      )}
    </div>
  );
}
