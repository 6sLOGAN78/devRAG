import { CircleAlert, CircleCheck, CircleSlash, File as FileIcon, Loader2, X } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { formatBytes, lastExtension } from "./file-rules";
import type { QueueRow, RowFailure } from "./upload-queue";

function failureText(failure: RowFailure | null, t: TFunction, maxBytes: string): string {
  switch (failure?.kind) {
    case "message":
      return failure.text;
    case "tooLarge":
      return t("upload.error.tooLarge", { max: maxBytes });
    case "limit":
      return t("upload.error.limit");
    case "network":
      return t("upload.error.network");
    case "server":
      return t("upload.error.server");
    default:
      return t("upload.error.rejected");
  }
}

/** The words for a row's state. Server text is returned as it came and is rendered as a text node only. */
export function rowStateText(row: QueueRow, t: TFunction, language: string, maxFileBytes: number): string {
  const max = formatBytes(maxFileBytes, language);
  switch (row.status) {
    case "ready":
      return t("upload.state.ready");
    case "rejected":
      switch (row.rejection) {
        case "folder":
          return t("upload.reject.folder");
        case "nameLong":
          return t("upload.reject.nameLong");
        case "noExtension":
          return t("upload.reject.noExtension");
        case "empty":
          return t("upload.reject.empty");
        case "size":
          return t("upload.reject.size", { size: formatBytes(row.size, language), max });
        default:
          return t("upload.reject.extension", { ext: `.${lastExtension(row.name)}` });
      }
    case "uploading":
      return t("upload.state.percent", { percent: row.percent });
    case "finishing":
      return t("upload.state.finishing");
    case "done":
      return row.savedName === null ? t("upload.state.done") : t("upload.state.renamed", { name: row.savedName });
    case "failed":
      return failureText(row.failure, t, max);
    case "cancelled":
      return t("upload.state.cancelled");
  }
}

export interface UploadRowProps {
  row: QueueRow;
  maxFileBytes: number;
  onRemove: (id: number) => void;
  onCancel: (id: number) => void;
  onRetry: (id: number) => void;
}

/** One file of the list: state icon, name, size, state text, a bar while uploading and one trailing action. */
export function UploadRow({ row, maxFileBytes, onRemove, onCancel, onRetry }: UploadRowProps) {
  const { t, i18n } = useTranslation();
  const bad = row.status === "rejected" || row.status === "failed";
  const running = row.status === "uploading" || row.status === "finishing";

  const icon = (() => {
    const base = "mt-0.5 size-4 shrink-0";
    if (bad) return <CircleAlert className={cn(base, "text-destructive")} aria-hidden="true" />;
    if (running) return <Loader2 className={cn(base, "animate-spin motion-reduce:animate-none")} aria-hidden="true" />;
    if (row.status === "done") return <CircleCheck className={cn(base, "text-success")} aria-hidden="true" />;
    if (row.status === "cancelled") return <CircleSlash className={cn(base, "text-muted-foreground")} aria-hidden="true" />;
    return <FileIcon className={cn(base, "text-muted-foreground")} aria-hidden="true" />;
  })();

  const action = (() => {
    const ghost = { type: "button", variant: "ghost", size: "icon", "data-row-action": "" } as const;
    if (row.status === "ready" || row.status === "rejected") {
      return (
        <Button {...ghost} data-testid="upload-row-remove" aria-label={t("upload.row.remove", { name: row.name })} onClick={() => onRemove(row.id)}>
          <X aria-hidden="true" />
        </Button>
      );
    }
    if (row.status === "uploading") {
      return (
        <Button {...ghost} data-testid="upload-row-cancel" aria-label={t("upload.row.cancel", { name: row.name })} onClick={() => onCancel(row.id)}>
          <X aria-hidden="true" />
        </Button>
      );
    }
    if (row.status === "failed" || row.status === "cancelled") {
      return (
        <Button type="button" variant="outline" size="sm" data-row-action="" data-testid="upload-row-retry" aria-label={t("upload.row.retryLabel", { name: row.name })} onClick={() => onRetry(row.id)}>
          {t("upload.row.retry")}
        </Button>
      );
    }
    return null;
  })();

  return (
    <li data-testid="upload-row" data-row-id={row.id} className="flex flex-col gap-2 py-3">
      <div className="flex items-start gap-3">
        {icon}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 break-all text-sm font-semibold" title={row.name}>
            {row.name}
          </p>
          <p className="mt-1 flex flex-wrap gap-x-3 text-xs font-normal">
            <span className="tabular-nums text-muted-foreground">{formatBytes(row.size, i18n.language)}</span>
            <span data-testid="upload-row-state" className={cn(bad ? "text-destructive" : "text-muted-foreground")}>
              {rowStateText(row, t, i18n.language, maxFileBytes)}
            </span>
          </p>
        </div>
        {action}
      </div>
      {running ? (
        <Progress
          data-testid="upload-row-progress"
          label={t("upload.row.progress", { name: row.name })}
          value={row.status === "finishing" ? 100 : row.percent}
          valueText={row.status === "finishing" ? t("upload.state.finishing") : undefined}
        />
      ) : null}
    </li>
  );
}
