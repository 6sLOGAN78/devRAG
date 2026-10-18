import { useQuery } from "@tanstack/react-query";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { fetchPageImage } from "@/services/page-service";
import { useBlobUrl } from "./use-blob-url";

/** Rendered pages are immutable for a parse: kept as long as they are used, and for a minute after the last view. */
export const PAGE_IMAGE_GC_MS = 60000;

export const pageImageKey = (tenantId: string | null, datasetId: string, docId: string, page: number) => ["ws", tenantId, "page-image", datasetId, docId, page] as const;

export interface PageImage {
  /** An object URL for the page, or null while there is none (loading, failed, disabled). */
  url: string | null;
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
}

/**
 * One page image as an object URL (UI-SPEC HTTP client rules). The bytes come through the HTTP client, so the
 * Authorization header travels as a header and no token is put in a URL. `fetchPageImage` has already refused any type
 * other than JPEG and PNG, so a URL is made only for those. The URL comes from `useBlobUrl`, the only place an object URL
 * is made; it is revoked when the page, the document or the component changes.
 */
export function usePageImage(datasetId: string, docId: string, page: number, enabled = true): PageImage {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const query = useQuery({
    queryKey: pageImageKey(tenantId, datasetId, docId, page),
    queryFn: ({ signal }) => fetchPageImage(datasetId, docId, page, signal),
    staleTime: Infinity,
    gcTime: PAGE_IMAGE_GC_MS,
    retry: false,
    enabled: enabled && tenantId !== null && datasetId !== "" && docId !== "",
  });
  // A URL made for another blob has been revoked: `useBlobUrl` never hands it out.
  const url = useBlobUrl(query.data);
  return {
    url,
    isLoading: url === null && !query.isError,
    isError: query.isError,
    refetch: () => void query.refetch(),
  };
}
