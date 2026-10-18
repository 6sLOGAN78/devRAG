import { EllipsisVertical, Loader2 } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { chunkPath, documentViewerPath } from "@/constants/app-paths";
import type { DocumentView } from "@/services/document-service";
import type { ParseActions } from "./parse-actions";

export interface DocumentRowActionsProps {
  datasetId: string;
  document: DocumentView;
  /** May the caller parse, cancel and switch this document (D-02)? Controls the caller may not use are absent. */
  canChange: boolean;
  actions: ParseActions;
  /** Opens the details sheet. The menu item exists only when this is given and a log exists; focus returns to the menu button. */
  onShowDetails?: (logId: string, opener: HTMLElement) => void;
}

type Inline = "parse" | "cancel" | "again" | null;

/** The one inline button a state offers: Parse, Cancel parsing or Parse again. A finished document offers none. */
function inlineOf(document: DocumentView): Inline {
  if (document.run === "0") return document.parseable ? "parse" : null;
  if (document.run === "1") return "cancel";
  if (document.run === "2" || document.run === "4") return "again";
  return null;
}

/**
 * The inline parse control and the overflow menu of one row. The menu is not modal and closes first when it opens the
 * re-parse dialog, so the dialog (not the menu) takes focus and hands it back to the menu button when it closes.
 */
export function DocumentRowActions({ datasetId, document, canChange, actions, onShowDetails }: DocumentRowActionsProps) {
  const { t } = useTranslation();
  const chosen = useRef(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const inline = canChange ? inlineOf(document) : null;
  const busy = actions.isBusy(document.id);
  const showDetails = document.lastLogId !== null && onShowDetails !== undefined;
  const canReparse = canChange && document.run === "3";

  let inlineButton = null;
  if (inline !== null) {
    const spec = {
      parse: { id: "document-parse", text: t("datasets.parse.action"), label: t("datasets.parse.actionLabel", { name: document.name }), run: () => actions.parse([document.id]) },
      cancel: { id: "document-cancel", text: t("datasets.parse.cancel"), label: t("datasets.parse.cancelLabel", { name: document.name }), run: () => actions.cancel([document.id]) },
      again: { id: "document-reparse", text: t("datasets.parse.again"), label: t("datasets.parse.againLabel", { name: document.name }), run: () => actions.parse([document.id]) },
    }[inline];
    inlineButton = (
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-testid={spec.id}
        aria-label={spec.label}
        aria-disabled={busy ? true : undefined}
        aria-busy={busy || undefined}
        className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
        onClick={() => {
          if (!busy) void spec.run();
        }}
      >
        {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {spec.text}
      </Button>
    );
  }

  return (
    <div className="flex items-center justify-end gap-1">
      {inlineButton}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button ref={trigger} type="button" variant="ghost" size="icon" data-testid="document-more" aria-label={t("datasets.files.more", { name: document.name })}>
            <EllipsisVertical aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          data-testid="document-menu"
          onCloseAutoFocus={(event) => {
            if (chosen.current) event.preventDefault();
            chosen.current = false;
          }}
        >
          <DropdownMenuItem asChild data-testid="document-menu-chunks">
            <Link to={chunkPath(datasetId, document.id)}>{t("datasets.files.menu.viewChunks")}</Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild data-testid="document-menu-open">
            <Link to={documentViewerPath(datasetId, document.id)}>{t("datasets.files.menu.open")}</Link>
          </DropdownMenuItem>
          {showDetails ? (
            <DropdownMenuItem
              data-testid="document-menu-details"
              onSelect={() => {
                chosen.current = true;
                if (document.lastLogId !== null && trigger.current !== null) onShowDetails?.(document.lastLogId, trigger.current);
              }}
            >
              {t("datasets.files.menu.details")}
            </DropdownMenuItem>
          ) : null}
          {canReparse ? (
            <DropdownMenuItem
              data-testid="document-menu-reparse"
              onSelect={() => {
                chosen.current = true;
                void actions.parse([document.id]);
              }}
            >
              {t("datasets.files.menu.reparse")}
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
