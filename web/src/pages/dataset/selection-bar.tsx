import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export interface SelectionBarProps {
  /** Documents selected on this page. */
  count: number;
  /** Selected documents that are not parsing, and selected documents that are. */
  parseCount: number;
  cancelCount: number;
  /** A request for the selection is in flight. */
  busy: boolean;
  onParse: () => void;
  onCancel: () => void;
  onClear: () => void;
  onMetadata?: () => void;
}

/** Appears above the table while documents are selected (D-01). Counts come from the selected rows, never the page. */
export function SelectionBar({ count, parseCount, cancelCount, busy, onParse, onCancel, onClear, onMetadata }: SelectionBarProps) {
  const { t } = useTranslation();
  const guard = (action: () => void) => () => {
    if (!busy) action();
  };
  const busyProps = { "aria-disabled": busy ? true : undefined, "aria-busy": busy || undefined, className: "aria-disabled:pointer-events-none aria-disabled:opacity-50" } as const;
  return (
    <div role="toolbar" aria-label={t("datasets.parse.selection.toolbar")} data-testid="selection-bar" className="flex flex-wrap items-center gap-3 rounded-lg bg-muted p-4">
      <p aria-live="polite" data-testid="selection-count" className="text-sm font-semibold">
        {t("datasets.parse.selection.count", { count })}
      </p>
      {parseCount > 0 ? (
        <Button type="button" variant="outline" data-testid="selection-parse" onClick={guard(onParse)} {...busyProps}>
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("datasets.parse.selection.parse", { count: parseCount })}
        </Button>
      ) : null}
      {cancelCount > 0 ? (
        <Button type="button" variant="outline" data-testid="selection-cancel" onClick={guard(onCancel)} {...busyProps}>
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("datasets.parse.selection.cancel", { count: cancelCount })}
        </Button>
      ) : null}
      {onMetadata ? <Button type="button" variant="outline" data-testid="selection-metadata" onClick={guard(onMetadata)} {...busyProps}>{t("datasets.metadata.editSelected")}</Button> : null}
      <Button type="button" variant="ghost" data-testid="selection-clear" onClick={onClear}>
        {t("datasets.parse.selection.clear")}
      </Button>
    </div>
  );
}
