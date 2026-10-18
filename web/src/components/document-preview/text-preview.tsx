import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { fetchTextPreview } from "@/services/page-service";

/** The most characters of a file the viewer shows (UI-SPEC viewer table). */
export const MAX_PREVIEW_CHARS = 262144;
const SKELETON_LINES = 8;

export function PreviewError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="viewer-preview-error" role="alert" className="flex flex-col items-start gap-2">
      <p className="text-sm">{t("viewer.previewError")}</p>
      <Button type="button" variant="outline" onClick={onRetry}>
        {t("errorState.action")}
      </Button>
    </div>
  );
}

export interface TextPreviewProps {
  datasetId: string;
  docId: string;
  /** False until the workspace is bound (FE-02). */
  enabled?: boolean;
}

/**
 * The text of a text-like file in a `<pre>`. Text nodes only: HTML shows as its source and Markdown is not rendered
 * (T-04-32-01). At most 262144 characters are shown; a cut by the server or here adds a line under the box.
 */
export function TextPreview({ datasetId, docId, enabled = true }: TextPreviewProps) {
  const { t } = useTranslation();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const query = useQuery({
    queryKey: ["ws", tenantId, "text-preview", datasetId, docId],
    queryFn: ({ signal }) => fetchTextPreview(datasetId, docId, signal),
    retry: false,
    enabled: enabled && tenantId !== null && datasetId !== "" && docId !== "",
  });

  if (query.isError) return <PreviewError onRetry={() => void query.refetch()} />;
  if (query.data === undefined) {
    return (
      <div className="flex flex-col gap-2">
        <p role="status" className="sr-only">
          {t("viewer.loading")}
        </p>
        {Array.from({ length: SKELETON_LINES }, (_, index) => (
          <Skeleton key={index} data-testid="viewer-text-skeleton" className="h-4 w-full" aria-hidden="true" />
        ))}
      </div>
    );
  }
  const { text, cut } = query.data;
  if (text === "") return <p className="text-sm text-muted-foreground">{t("viewer.text.empty")}</p>;
  const clipped = text.length > MAX_PREVIEW_CHARS;
  return (
    <div className="flex flex-col gap-2">
      <pre
        data-testid="viewer-text"
        tabIndex={0}
        aria-label={t("viewer.text.label")}
        className="max-h-[calc(100vh-16rem)] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background p-4 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {clipped ? text.slice(0, MAX_PREVIEW_CHARS) : text}
      </pre>
      {cut || clipped ? (
        <p data-testid="viewer-text-cut" className="text-xs font-normal text-muted-foreground">
          {t("viewer.text.cut")}
        </p>
      ) : null}
    </div>
  );
}
