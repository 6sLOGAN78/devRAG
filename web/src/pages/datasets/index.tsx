import { Database, Plus, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { CreateDatasetDialog } from "@/components/create-dataset-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { MODEL_SETTINGS_PATH } from "@/constants/app-paths";
import { DATASETS_PAGE_SIZE, useDatasetsRequest } from "@/hooks/use-knowledge-request";
import { useDefaultsRequest } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { MAX_KEYWORDS_LENGTH } from "@/services/dataset-service";
import { DatasetCard } from "./dataset-card";

const SKELETON_CARDS = 8;
/** An absurd `page` in the URL is capped here; the server answers an empty page and the gallery steps back. */
const MAX_PAGE = 100000;

/** `page` from the URL: a whole number of at least 1, otherwise 1 (T-03-30-03). */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return 1;
  return Math.min(MAX_PAGE, Math.max(1, Number(raw)));
}

/** `keywords` from the URL, cut to the length the API accepts before any request is built. */
function parseKeywords(raw: string | null): string {
  return (raw ?? "").slice(0, MAX_KEYWORDS_LENGTH);
}

function CardsSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="dataset-grid-skeleton" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <p role="status" className="sr-only">
        {t("datasets.loading")}
      </p>
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <Skeleton key={index} data-testid="dataset-card-skeleton" className="h-40 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * Datasets gallery (UI-10, KB-04). Lists the active workspace's visible datasets, twelve a page, with `page` and
 * `keywords` kept in the URL and clamped before they reach a request. Switching workspace resets both (D-26). The
 * missing-default notice (D-18) is shown while the workspace has no explicit default embedding model.
 */
export default function DatasetsPage() {
  const { t, i18n } = useTranslation();
  const workspace = useActiveWorkspace();
  const tenantId = workspace?.tenantId ?? null;
  const canManage = workspace?.role === "owner" || workspace?.role === "admin";
  const [params, setParams] = useSearchParams();
  const page = parsePage(params.get("page"));
  const keywords = parseKeywords(params.get("keywords"));
  const datasets = useDatasetsRequest({ page, keywords });
  const defaults = useDefaultsRequest();
  const [creating, setCreating] = useState(false);
  const previousTenant = useRef(tenantId);
  const trigger = useRef<HTMLElement | null>(null);
  const pageRoot = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.title = t("datasets.documentTitle");
  }, [t, i18n.language]);

  // A different workspace is a different gallery: back to page 1 with no search, and no dialog left open (D-26).
  useEffect(() => {
    if (previousTenant.current === tenantId) return;
    previousTenant.current = tenantId;
    setCreating(false);
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("page");
        next.delete("keywords");
        return next;
      },
      { replace: true },
    );
  }, [tenantId, setParams]);

  const total = datasets.data?.total ?? 0;
  const items = datasets.data?.items ?? [];
  const pages = Math.max(1, Math.ceil(total / DATASETS_PAGE_SIZE));
  const pastEnd = datasets.data !== undefined && items.length === 0 && total > 0 && page > pages;

  function setPage(next: number): void {
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next <= 1) updated.delete("page");
        else updated.set("page", String(next));
        return updated;
      },
      { replace: false },
    );
  }

  // After the last page empties (a delete elsewhere) step back to the last page that exists.
  useEffect(() => {
    if (pastEnd) {
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (pages <= 1) updated.delete("page");
          else updated.set("page", String(pages));
          return updated;
        },
        { replace: true },
      );
    }
  }, [pastEnd, pages, setParams]);

  function search(next: string): void {
    setParams((current) => {
      const updated = new URLSearchParams(current);
      updated.delete("page");
      if (next === "") updated.delete("keywords");
      else updated.set("keywords", next.slice(0, MAX_KEYWORDS_LENGTH));
      return updated;
    });
  }

  const searching = keywords !== "";
  const hasItems = items.length > 0;
  const showCreate = hasItems || searching;
  const createButton = (
    <Button
      type="button"
      data-testid="dataset-create"
      onClick={(event) => {
        trigger.current = event.currentTarget;
        setCreating(true);
      }}
    >
      <Plus aria-hidden="true" />
      {t("datasets.create")}
    </Button>
  );

  let body;
  if (datasets.isPending || pastEnd) {
    body = <CardsSkeleton />;
  } else if (datasets.isError) {
    body = <ErrorState heading={t("datasets.error.loadList")} onAction={() => void datasets.refetch()} />;
  } else if (!hasItems && searching) {
    body = (
      <EmptyState
        as="h2"
        icon={SearchX}
        heading={t("datasets.noMatch.heading", { keywords })}
        body={t("datasets.noMatch.body")}
        action={
          <Button type="button" variant="link" onClick={() => search("")}>
            {t("common.search.clear")}
          </Button>
        }
      />
    );
  } else if (!hasItems) {
    body = <EmptyState as="h2" icon={Database} heading={t("datasets.empty.heading")} body={t("datasets.empty.body")} action={createButton} />;
  } else {
    body = (
      <>
        <div data-testid="dataset-grid" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((dataset) => (
            <DatasetCard key={dataset.id} dataset={dataset} />
          ))}
        </div>
        <Pagination
          page={page}
          pages={pages}
          onPageChange={setPage}
          previousLabel={t("common.pagination.previous")}
          nextLabel={t("common.pagination.next")}
          statusLabel={t("common.pagination.status", { page, pages })}
        />
      </>
    );
  }

  /** Back to the button that opened the dialog; if it was replaced (the empty state's button became the header's), the header button. */
  function restoreFocus(event: Event): void {
    event.preventDefault();
    const target = trigger.current?.isConnected === true ? trigger.current : pageRoot.current?.querySelector<HTMLElement>('[data-testid="dataset-create"]');
    target?.focus();
  }

  const missingDefault = defaults.data !== undefined && defaults.data.embedding === "";

  return (
    <div ref={pageRoot} data-testid="datasets-page" className="flex flex-col gap-6">
      <PageHeader title={t("datasets.title")} actions={showCreate ? createButton : undefined} />
      <p className="max-w-prose text-sm font-normal text-muted-foreground">{t("datasets.intro", { workspace: workspace?.name ?? "" })}</p>
      {missingDefault ? (
        <Alert variant="info" data-testid="datasets-missing-default">
          {canManage ? (
            <>
              {t("datasets.missingDefault.manager")}{" "}
              <Link to={MODEL_SETTINGS_PATH} className="underline underline-offset-2">
                {t("datasets.missingDefault.link")}
              </Link>
            </>
          ) : (
            t("datasets.missingDefault.member")
          )}
        </Alert>
      ) : null}
      {showCreate ? (
        <div data-testid="datasets-search" className="max-w-sm">
          <SearchInput value={keywords} onSearch={search} label={t("datasets.search")} clearLabel={t("common.search.clear")} />
        </div>
      ) : null}
      {body}
      <CreateDatasetDialog open={creating} onOpenChange={setCreating} onCloseAutoFocus={restoreFocus} />
    </div>
  );
}
