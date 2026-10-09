import { Lock, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { datasetFilesPath } from "@/constants/app-paths";
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
 * render as text nodes. Plan 03-25 mounts the dataset actions menu inside this article, above the link layer (relative
 * and z-10), for the creator, owners and admins only; there is no menu or stub here.
 */
export function DatasetCard({ dataset }: { dataset: DatasetView }) {
  const { t, i18n } = useTranslation();
  const shared = dataset.permission === "team";
  const VisibilityIcon = shared ? Users : Lock;
  const updated = updatedText(dataset.updateTime, i18n.language);
  return (
    <article
      data-testid="dataset-card"
      className="relative flex min-h-40 flex-col gap-2 rounded-lg border bg-card p-6 text-card-foreground hover:border-foreground/20 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background"
    >
      <h2 className="line-clamp-2 break-words text-xl font-semibold leading-tight">
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
    </article>
  );
}
