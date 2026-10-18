import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export interface ChunkNoticesProps {
  readOnly: boolean;
  documentOff: boolean;
  parsing: boolean;
  partial: boolean;
  /** The document has a run whose details can be shown. */
  canOpenDetails: boolean;
  /** Receives the link-button so focus can return to it when the sheet closes. */
  onDetails: (opener: HTMLElement) => void;
}

/** The info notices above the inspector body, in the order of the UI-SPEC. Each one is a polite status. */
export function ChunkNotices({ readOnly, documentOff, parsing, partial, canOpenDetails, onDetails }: ChunkNoticesProps) {
  const { t } = useTranslation();
  if (!readOnly && !documentOff && !parsing && !partial) return null;
  return (
    <div className="flex flex-col gap-2">
      {readOnly ? (
        <Alert variant="info" data-testid="chunk-readonly-notice">
          {t("inspector.notice.readOnly")}
        </Alert>
      ) : null}
      {documentOff ? (
        <Alert variant="info" data-testid="chunk-document-off-notice">
          {t("inspector.notice.documentOff")}
        </Alert>
      ) : null}
      {parsing ? (
        <Alert variant="info" data-testid="chunk-parsing-notice">
          {t("inspector.notice.parsing")}
        </Alert>
      ) : null}
      {partial ? (
        <Alert variant="info" data-testid="chunk-partial-notice">
          <span>{t("inspector.notice.partial")} </span>
          {canOpenDetails ? (
            <Button type="button" variant="link" size="sm" className="h-auto p-0 text-sm" onClick={(event) => onDetails(event.currentTarget)}>
              {t("datasets.files.detailsLink")}
            </Button>
          ) : null}
        </Alert>
      ) : null}
    </div>
  );
}
