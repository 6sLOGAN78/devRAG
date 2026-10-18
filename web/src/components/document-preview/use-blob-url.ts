import { useEffect, useState } from "react";
import { isDisplayableImage } from "@/services/page-service";

/**
 * The single place an object URL is made (UI-SPEC HTTP client rules). `useBlobUrl` returns a URL only for an
 * `image/jpeg` or `image/png` blob; any other type, or no blob, gives null. The URL is revoked when the blob changes
 * and when the component goes away, and is never handed out for a blob other than the one it was made for.
 */
export function useBlobUrl(blob: Blob | null | undefined): string | null {
  const [made, setMade] = useState<{ blob: Blob; url: string } | null>(null);

  useEffect(() => {
    if (blob === null || blob === undefined || !isDisplayableImage(blob.type)) {
      setMade(null);
      return;
    }
    const url = URL.createObjectURL(blob);
    setMade({ blob, url });
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  return made !== null && made.blob === blob ? made.url : null;
}

/**
 * Saves a downloaded file through a temporary link whose `download` attribute is the document's name. The blob is
 * re-typed as an opaque binary first, so a stored HTML file is saved, never opened as a page by the SPA. The URL is
 * revoked straight after the click.
 */
export function saveBlobAs(blob: Blob, name: string): void {
  const url = URL.createObjectURL(new Blob([blob], { type: "application/octet-stream" }));
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.rel = "noopener";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
