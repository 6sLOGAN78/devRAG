import { Download as DownloadIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { Download } from "@/components/document-preview/use-download";

export interface DownloadButtonProps {
  download: Download;
  name: string;
  testId: string;
  /** The header button names the file ("Download {name}"); the card button says "Download". */
  named: boolean;
}

/** An outline Download button. While it runs it is busy and reads the progress; a second press does nothing. */
export function DownloadButton({ download, name, testId, named }: DownloadButtonProps) {
  const { t } = useTranslation();
  const { busy, percent, start } = download;
  let label = t("viewer.download");
  if (busy) label = percent === null ? t("viewer.downloading") : t("viewer.downloadingPercent", { percent });
  return (
    <Button
      type="button"
      variant="outline"
      data-testid={testId}
      aria-label={!busy && named ? t("viewer.downloadLabel", { name }) : undefined}
      aria-disabled={busy}
      aria-busy={busy ? "true" : undefined}
      onClick={() => !busy && start()}
    >
      <DownloadIcon aria-hidden="true" />
      {label}
    </Button>
  );
}
