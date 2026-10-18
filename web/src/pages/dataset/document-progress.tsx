import { useTranslation } from "react-i18next";
import { Progress } from "@/components/ui/progress";
import type { DocumentView } from "@/services/document-service";

/** Slack so 0.29 * 100 (28.999999999999996) does not floor to 28. */
const EPSILON = 1e-6;
const RUNNING_CAP = 99;

/**
 * Server progress is a fraction of one. The table shows whole percent rounded DOWN, and never 100 while the parse still
 * runs: only a finished document shows 100 (FE-18: 0.996 is 99, not 100).
 */
export function percentOf(document: Pick<DocumentView, "run" | "progress">): number {
  if (document.run === "3") return 100;
  const whole = Math.floor(Math.min(1, Math.max(0, document.progress)) * 100 + EPSILON);
  return Math.min(RUNNING_CAP, whole);
}

/** The progress cell: a bar and the latest server message while parsing, a percentage otherwise, an em dash when failed. */
export function DocumentProgress({ document }: { document: Pick<DocumentView, "name" | "run" | "progress" | "progressMessage"> }) {
  const { t } = useTranslation();
  const percent = percentOf(document);
  const text = t("datasets.files.progress.percent", { percent });
  if (document.run === "4") {
    return (
      <>
        <span aria-hidden="true">{"—"}</span>
        <span className="sr-only">{t("datasets.files.progress.none")}</span>
      </>
    );
  }
  if (document.run !== "1") return <>{text}</>;
  const message = document.progressMessage !== "" ? document.progressMessage : t("datasets.files.progress.waiting");
  return (
    <div className="flex min-w-40 max-w-56 flex-col gap-1">
      <div className="flex items-center gap-2">
        <Progress value={percent} label={t("datasets.files.progress.label", { name: document.name })} data-testid="document-progress-bar" />
        <span>{text}</span>
      </div>
      <p title={message} data-testid="document-progress-message" className="truncate text-xs font-normal text-muted-foreground">
        {message}
      </p>
    </div>
  );
}
