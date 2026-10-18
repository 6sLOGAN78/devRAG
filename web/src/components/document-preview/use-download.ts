import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { downloadDocument } from "@/services/page-service";
import { notifyError } from "@/services/notify";
import { saveBlobAs } from "./use-blob-url";

export interface Download {
  start: () => void;
  /** Whole percent of the file received, or null while the size is unknown or nothing runs. */
  percent: number | null;
  busy: boolean;
}

/**
 * Downloads a document as a blob through the HTTP client (no timeout, no token in a URL) and saves it under its name.
 * A second `start` while one runs does nothing; leaving the page aborts the request and saves nothing.
 */
export function useDownload(datasetId: string, docId: string, name: string): Download {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [percent, setPercent] = useState<number | null>(null);
  const running = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      controller.current?.abort();
    };
  }, []);

  const start = useCallback(() => {
    if (running.current) return;
    running.current = true;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setPercent(null);
    void (async () => {
      try {
        const blob = await downloadDocument(datasetId, docId, {
          signal: abort.signal,
          onProgress: (loaded, total) => {
            if (!alive.current) return;
            setPercent(total !== undefined && total > 0 ? Math.min(100, Math.floor((loaded / total) * 100)) : null);
          },
        });
        if (abort.signal.aborted) return;
        saveBlobAs(blob, name);
      } catch {
        if (!abort.signal.aborted) notifyError({ title: t("viewer.downloadFailed"), description: "", id: "viewer-download-failed" });
      } finally {
        running.current = false;
        controller.current = null;
        if (alive.current) {
          setBusy(false);
          setPercent(null);
        }
      }
    })();
  }, [datasetId, docId, name, t]);

  return { start, percent, busy };
}
