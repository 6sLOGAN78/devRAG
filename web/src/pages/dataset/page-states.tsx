import { SearchX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DATASETS_PATH } from "@/constants/app-paths";

/**
 * The one block shown for a dataset that is missing, deleted, private to someone else, in a workspace the caller has not
 * joined, or named by a malformed `id` (D-27, T-03-31-01). Nothing in it tells those cases apart. No back link and no
 * header actions: the primary button is the way out.
 */
export function DatasetNotFound() {
  const { t } = useTranslation();
  return (
    <div data-testid="dataset-not-found">
      <EmptyState
        icon={SearchX}
        heading={t("dataset.notFound.heading")}
        body={t("dataset.notFound.body")}
        action={
          <Button asChild>
            <Link to={DATASETS_PATH}>{t("dataset.notFound.action")}</Link>
          </Button>
        }
      />
    </div>
  );
}

/** Header and table placeholders while the dataset loads. */
export function DatasetPageSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="dataset-page-skeleton" className="flex flex-col gap-6">
      <p role="status" className="sr-only">
        {t("dataset.loading")}
      </p>
      <Skeleton className="h-8 w-[200px]" aria-hidden="true" />
      <Skeleton className="h-4 w-64" aria-hidden="true" />
      <div className="flex flex-col rounded-lg border">
        <Skeleton className="h-10 w-full rounded-none" aria-hidden="true" />
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-12 w-full rounded-none border-b border-background" aria-hidden="true" />
        ))}
      </div>
    </div>
  );
}
