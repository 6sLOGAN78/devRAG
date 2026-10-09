import { FileUp, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatBytes, resolveUploadLimits } from "@/components/file-upload-dialog/file-rules";
import { DeleteDocumentDialog } from "@/components/delete-document-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DOCUMENTS_PAGE_SIZE, useDocumentsRequest } from "@/hooks/use-document-request";
import type { UploadLimitsView } from "@/services/dataset-service";
import { MAX_DOCUMENT_KEYWORDS_LENGTH, type DocumentView } from "@/services/document-service";
import { DocumentRow } from "./document-row";

const SKELETON_ROWS = 5;
const COLUMNS = ["name", "size", "uploaded", "status", "progress", "actions"] as const;

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

  const showToolbar = items.length > 0 || searching || (documents.isPending && seenDocuments);
  const maxFile = formatBytes(resolveUploadLimits(limits).maxFileBytes, i18n.language);

  let body;
  if (documents.isPending || pastEnd) {
    body = <TableSkeleton />;
  } else if (documents.isError) {
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
            {COLUMNS.map((column) => (
              <TableHead key={column} className={column === "actions" ? "text-right" : undefined}>
                {t(`datasets.files.col.${column}`)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((document) => (
            <DocumentRow key={document.id} dataset={dataset} document={document} onDelete={askDelete} />
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {showToolbar ? (
        <div data-testid="documents-search" className="max-w-sm">
          <SearchInput
            value={keywords}
            onSearch={(next) => onSearch(next.slice(0, MAX_DOCUMENT_KEYWORDS_LENGTH))}
            label={t("datasets.files.search")}
            clearLabel={t("common.search.clear")}
          />
        </div>
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
