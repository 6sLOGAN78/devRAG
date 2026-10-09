import { Circle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

/**
 * A document's parse state as the table shows it (UI-SPEC choice 22). In Phase 3 nothing parses, so `run` "0" (not
 * started) is the only state a document has: a `default` badge with a hollow circle. Any other value is shown as an
 * outline "Unknown status" so an unexpected value is visible rather than mislabelled. No Parse control exists; Phase 4
 * replaces the second branch with the documented states.
 */
export function DocumentStatusBadge({ run }: { run: string }) {
  const { t } = useTranslation();
  if (run === "0") {
    return (
      <Badge variant="default" data-testid="document-status">
        <Circle className="size-3" aria-hidden="true" />
        {t("datasets.files.status.notStarted")}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" data-testid="document-status">
      {t("datasets.files.status.unknown")}
    </Badge>
  );
}
