import { FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { formatBytes } from "@/components/file-upload-dialog/file-rules";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { TableCell, TableRow } from "@/components/ui/table";
import { chunkPath } from "@/constants/app-paths";
import { useCanChangeDocument, useCanRemoveDocument } from "@/hooks/use-dataset-permissions";
import { cn } from "@/lib/utils";
import type { DocumentView } from "@/services/document-service";
import { DocumentProgress } from "./document-progress";
import { DocumentRowActions } from "./document-row-actions";
import { DocumentStatusBadge } from "./document-status-badge";
import type { ParseActions } from "./parse-actions";

export interface RowDataset {
  id: string;
  createdBy: string;
  tenantId: string;
}

/** The upload time as a machine value and a localized medium date, or null when the server sent no usable timestamp. */
function uploadedOf(document: DocumentView, language: string): { iso: string; text: string } | null {
  const stamp = document.createTime > 0 ? document.createTime : document.updateTime;
  if (stamp <= 0) return null;
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) return null;
  return { iso: date.toISOString(), text: new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(date) };
}

/** A thumbnail from the vetted `thumbnail` field; a picture that fails to decode becomes the file icon. */
function Thumbnail({ source }: { source: string | null }) {
  const [broken, setBroken] = useState(false);
  if (source === null || broken) return <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />;
  return <img src={source} alt="" loading="lazy" data-testid="document-thumbnail" onError={() => setBroken(true)} className="h-10 w-8 shrink-0 rounded-sm border object-cover" />;
}

interface DocumentRowProps {
  dataset: RowDataset;
  document: DocumentView;
  actions: ParseActions;
  /** The select column is drawn on this page (some row qualifies). */
  selectColumn: boolean;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onDelete: (document: DocumentView, opener: HTMLButtonElement) => void;
  onShowDetails?: (logId: string) => void;
}

/**
 * One document. The file name, progress line and failure reason are server or user text and render as text nodes only.
 * Controls follow D-02 and D-10: whoever may change the document gets the checkbox, the search switch, the parse
 * button and the menu items that change it; everyone else sees status, progress, read-only On or Off text and the menu
 * with the read-only items. The delete icon exists only where the caller may delete the document (D-09).
 */
export function DocumentRow({ dataset, document, actions, selectColumn, selected, onSelect, onDelete, onShowDetails }: DocumentRowProps) {
  const { t, i18n } = useTranslation();
  const canRemove = useCanRemoveDocument(dataset, document);
  const canChange = useCanChangeDocument(dataset, document);
  const uploaded = uploadedOf(document, i18n.language);
  const running = document.run === "1";
  const selectable = canChange && (document.parseable || running);
  const showDetailsLink = (document.run === "4" || document.run === "2") && document.lastLogId !== null && onShowDetails !== undefined;
  return (
    <TableRow data-testid="document-row" data-run={document.run} data-doc-id={document.id} className="min-h-12">
      {selectColumn ? (
        <TableCell className="w-12 px-2">
          {selectable ? (
            <Checkbox checked={selected} onChange={onSelect} aria-label={t("datasets.files.selectLabel", { name: document.name })} data-testid="document-select" />
          ) : null}
        </TableCell>
      ) : null}
      <TableCell>
        <div className="flex items-start gap-2">
          <Thumbnail source={document.thumbnail} />
          <Link
            to={chunkPath(dataset.id, document.id)}
            title={document.name}
            data-testid="document-name-link"
            className={cn(
              "line-clamp-2 break-all rounded-sm underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              document.enabled ? "text-foreground" : "text-muted-foreground",
            )}
          >
            {document.name}
          </Link>
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{formatBytes(document.size, i18n.language)}</TableCell>
      <TableCell className="whitespace-nowrap">{uploaded === null ? t("common.notSet") : <time dateTime={uploaded.iso}>{uploaded.text}</time>}</TableCell>
      <TableCell>
        <DocumentStatusBadge document={document} />
        {showDetailsLink ? (
          <Button
            type="button"
            variant="link"
            data-testid="document-details"
            aria-label={t("datasets.files.detailsLabel", { name: document.name })}
            className="h-auto p-0 text-xs"
            onClick={() => document.lastLogId !== null && onShowDetails?.(document.lastLogId)}
          >
            {t("datasets.files.detailsLink")}
          </Button>
        ) : null}
      </TableCell>
      <TableCell data-testid="document-progress" className="tabular-nums">
        <DocumentProgress document={document} />
      </TableCell>
      <TableCell className="whitespace-nowrap">
        {canChange ? (
          <Switch
            checked={document.enabled}
            onChange={(next) => void actions.setEnabled(document.id, next)}
            busy={actions.isSwitching(document.id)}
            onLabel={t("datasets.files.inSearch.on")}
            offLabel={t("datasets.files.inSearch.off")}
            aria-label={t("datasets.files.inSearch.label", { name: document.name })}
            data-testid="document-search-switch"
          />
        ) : (
          <span data-testid="document-search-text" className="text-xs font-normal">
            {document.enabled ? t("datasets.files.inSearch.on") : t("datasets.files.inSearch.off")}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-1">
          <DocumentRowActions datasetId={dataset.id} document={document} canChange={canChange} actions={actions} onShowDetails={onShowDetails} />
          {canRemove ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              data-testid="document-delete"
              aria-label={t("datasets.files.deleteLabel", { name: document.name })}
              onClick={(event) => onDelete(document, event.currentTarget)}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  );
}
