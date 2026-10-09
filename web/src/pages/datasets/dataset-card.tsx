import { Lock, Users } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { DatasetActionsMenu } from "@/components/dataset-actions-menu";
import { DatasetSettingsDialog } from "@/components/dataset-settings-dialog";
import { DeleteDatasetDialog } from "@/components/delete-dataset-dialog";
import { Badge } from "@/components/ui/badge";
import { datasetFilesPath } from "@/constants/app-paths";
import { useCanManageDataset } from "@/hooks/use-dataset-permissions";
import type { DatasetView } from "@/services/dataset-service";

/** The "Updated {date}" text, or null when the server sent no usable timestamp. Dates follow the interface language. */
function updatedText(updateTime: number, language: string): string | null {
  if (updateTime <= 0) return null;
  const date = new Date(updateTime);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(date);
}

/**
 * One dataset in the gallery (UI-10). The name is the card's only link and its hit area covers the whole card
 * (`after:absolute after:inset-0`); the link target is built from the id alone. Name and description are user text and
 * render as text nodes. The actions menu (settings and delete) sits above the link layer and is drawn only for the
 * dataset's creator and the workspace owner and admins (D-09); it is absent, not disabled, for everyone else. The card
 * owns the two dialogs it opens; a closed dialog returns focus to the menu button, and after a delete the page decides
 * (`onDeleted`), because the card is gone by then.
 */
export function DatasetCard({ dataset, onDeleted }: { dataset: DatasetView; onDeleted?: () => void }) {
  const { t, i18n } = useTranslation();
  const canManage = useCanManageDataset(dataset);
  const [dialog, setDialog] = useState<"settings" | "delete" | null>(null);
  const menuButton = useRef<HTMLButtonElement | null>(null);
  const deleted = useRef(false);
  const shared = dataset.permission === "team";
  const VisibilityIcon = shared ? Users : Lock;
  const updated = updatedText(dataset.updateTime, i18n.language);

  /** Back to the menu button unless the dataset was deleted (its card, and so the button, is going away). */
  function returnFocus(event: Event): void {
    event.preventDefault();
    if (!deleted.current) menuButton.current?.focus();
  }

  return (
    <article
      data-testid="dataset-card"
      className="relative flex min-h-40 flex-col gap-2 rounded-lg border bg-card p-6 text-card-foreground hover:border-foreground/20 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background"
    >
      <h2 className={`line-clamp-2 break-words text-xl font-semibold leading-tight${canManage ? " pr-10" : ""}`}>
        <Link
          to={datasetFilesPath(dataset.id)}
          data-testid="dataset-card-link"
          className="rounded-sm after:absolute after:inset-0 focus-visible:outline-none"
        >
          {dataset.name}
        </Link>
      </h2>
      {dataset.description === "" ? null : <p className="line-clamp-2 break-words text-sm font-normal text-muted-foreground">{dataset.description}</p>}
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">
          <VisibilityIcon className="size-3" aria-hidden="true" />
          {shared ? t("datasets.visibility.team") : t("datasets.visibility.me")}
        </Badge>
      </div>
      <p className="mt-auto text-xs font-normal tabular-nums text-muted-foreground">
        <span>{t("datasets.card.documents", { count: dataset.docNum })}</span>
        {updated === null ? null : (
          <>
            <span aria-hidden="true"> · </span>
            <span>{t("datasets.card.updated", { date: updated })}</span>
          </>
        )}
      </p>
      {canManage ? (
        <>
          <div className="absolute right-2 top-2">
            <DatasetActionsMenu name={dataset.name} triggerRef={menuButton} onSettings={() => setDialog("settings")} onDelete={() => setDialog("delete")} />
          </div>
          <DatasetSettingsDialog dataset={dataset} open={dialog === "settings"} onOpenChange={(open) => setDialog(open ? "settings" : null)} onCloseAutoFocus={returnFocus} />
          <DeleteDatasetDialog
            dataset={{ id: dataset.id, name: dataset.name, tenantId: dataset.tenantId }}
            open={dialog === "delete"}
            onOpenChange={(open) => setDialog(open ? "delete" : null)}
            onSuccess={() => {
              deleted.current = true;
              onDeleted?.();
            }}
            onCloseAutoFocus={returnFocus}
          />
        </>
      ) : null}
    </article>
  );
}
