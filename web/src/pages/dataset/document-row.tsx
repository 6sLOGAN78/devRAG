import { FileText, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "@/components/file-upload-dialog/file-rules";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { useCanRemoveDocument } from "@/hooks/use-dataset-permissions";
import type { DocumentView } from "@/services/document-service";
import { DocumentStatusBadge } from "./document-status-badge";

export interface RowDataset {
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

/** Server progress is a fraction of one; the table shows whole percent. */
function percentOf(progress: number): number {
  return Math.round(Math.min(1, Math.max(0, progress)) * 100);
}

interface DocumentRowProps {
  dataset: RowDataset;
  document: DocumentView;
  onDelete: (document: DocumentView, opener: HTMLButtonElement) => void;
}

/**
 * One document. The file name is user text and renders as a text node only (never markup), clamped to two lines with
 * the full name in `title`. The delete icon exists only where the caller may delete the document (D-09): the dataset's
 * creator, the workspace owner and admins, or the member who uploaded it. Elsewhere the cell is empty.
 */
export function DocumentRow({ dataset, document, onDelete }: DocumentRowProps) {
  const { t, i18n } = useTranslation();
  const canRemove = useCanRemoveDocument(dataset, document);
  const uploaded = uploadedOf(document, i18n.language);
  return (
    <TableRow data-testid="document-row">
      <TableCell>
        <div className="flex items-start gap-2">
          <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span title={document.name} className="line-clamp-2 break-all">
            {document.name}
          </span>
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{formatBytes(document.size, i18n.language)}</TableCell>
      <TableCell className="whitespace-nowrap">
        {uploaded === null ? t("common.notSet") : <time dateTime={uploaded.iso}>{uploaded.text}</time>}
      </TableCell>
      <TableCell>
        <DocumentStatusBadge run={document.run} />
      </TableCell>
      <TableCell data-testid="document-progress" className="tabular-nums">
        {`${percentOf(document.progress)}%`}
      </TableCell>
      <TableCell className="text-right">
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
      </TableCell>
    </TableRow>
  );
}
