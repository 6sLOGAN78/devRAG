import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { downloadDocument, isDisplayableImage } from "@/services/page-service";
import { PreviewError } from "./text-preview";
import { useBlobUrl } from "./use-blob-url";

export interface ImagePreviewProps {
  datasetId: string;
  docId: string;
  /** The file name, used as the image's description. */
  name: string;
  /** False until the workspace is bound (FE-02). */
  enabled?: boolean;
}

/** An image file shown from a blob. Only `image/jpeg` and `image/png` are ever shown (T-04-32-02); anything else is the error state. */
export function ImagePreview({ datasetId, docId, name, enabled = true }: ImagePreviewProps) {
  const { t } = useTranslation();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const query = useQuery({
    queryKey: ["ws", tenantId, "content-image", datasetId, docId],
    queryFn: ({ signal }) => downloadDocument(datasetId, docId, { signal }),
    staleTime: Infinity,
    gcTime: 60000,
    retry: false,
    enabled: enabled && tenantId !== null && datasetId !== "" && docId !== "",
  });
  const blob = query.data;
  const url = useBlobUrl(blob);

  if (query.isError || (blob !== undefined && !isDisplayableImage(blob.type))) return <PreviewError onRetry={() => void query.refetch()} />;
  if (url === null) {
    return (
      <div>
        <p role="status" className="sr-only">
          {t("viewer.loading")}
        </p>
        <Skeleton data-testid="viewer-image-skeleton" className="h-[40vh] w-full" aria-hidden="true" />
      </div>
    );
  }
  return <img data-testid="viewer-image" src={url} alt={name} className="h-auto max-w-full rounded-md border border-border" />;
}
