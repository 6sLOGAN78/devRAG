import { Circle, CircleAlert, CircleCheck, CircleDashed, CircleSlash, Loader2, TriangleAlert, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { failureSentence } from "@/constants/failure-codes";
import type { DocumentView } from "@/services/document-service";

/** The states a document row can be in (UI-SPEC "Status map"); `unknown` keeps an unexpected `run` visible. */
export type StatusKind = "notStarted" | "unavailable" | "parsing" | "finished" | "failed" | "cancelled" | "partial" | "unknown";

type StatusInput = Pick<DocumentView, "run" | "chunkCount" | "parseable">;

/** `run`: "0" not started, "1" running, "2" cancelled, "3" finished, "4" failed. Failed and cancelled documents that kept chunks are partly indexed (D-07). */
export function statusKindOf(document: StatusInput): StatusKind {
  switch (document.run) {
    case "0":
      return document.parseable ? "notStarted" : "unavailable";
    case "1":
      return "parsing";
    case "3":
      return "finished";
    case "4":
      return document.chunkCount > 0 ? "partial" : "failed";
    case "2":
      return document.chunkCount > 0 ? "partial" : "cancelled";
    default:
      return "unknown";
  }
}

interface Look {
  variant: BadgeProps["variant"];
  icon: LucideIcon | null;
  key: string;
}

const LOOKS: Readonly<Record<StatusKind, Look>> = {
  notStarted: { variant: "default", icon: Circle, key: "datasets.files.status.notStarted" },
  unavailable: { variant: "outline", icon: CircleSlash, key: "datasets.files.status.unavailable" },
  parsing: { variant: "default", icon: Loader2, key: "datasets.files.status.parsing" },
  finished: { variant: "success", icon: CircleCheck, key: "datasets.files.status.finished" },
  failed: { variant: "destructive", icon: CircleAlert, key: "datasets.files.status.failed" },
  cancelled: { variant: "default", icon: CircleSlash, key: "datasets.files.status.cancelled" },
  partial: { variant: "degraded", icon: CircleDashed, key: "datasets.files.status.partial" },
  unknown: { variant: "outline", icon: null, key: "datasets.files.status.unknown" },
};

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

/** True while the user asks for reduced motion; false where `matchMedia` does not exist. */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(REDUCED_MOTION);
    const onChange = () => setReduced(query.matches);
    onChange();
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * A document's parse state as the table shows it: an icon and a word for every state (never colour alone), then the
 * detail lines of the status map. The failure reason is a fixed sentence for a known code, else the server's plain
 * message; it renders as a text node and is clamped to two lines.
 */
export function DocumentStatusBadge({ document }: { document: StatusInput & Partial<Pick<DocumentView, "error" | "pagesTotal" | "pagesWithoutText">> }) {
  const { t } = useTranslation();
  const reduced = useReducedMotion();
  const kind = statusKindOf(document);
  const look = LOOKS[kind];
  const Icon = look.icon;
  const spin = kind === "parsing" && !reduced ? "animate-spin" : undefined;

  const sentence = failureSentence(document.error);
  const reason = "key" in sentence ? t(sentence.key) : sentence.text;
  const skipped = document.pagesWithoutText ?? 0;
  const total = document.pagesTotal ?? 0;

  let detail: string | null = null;
  let detailClass = "text-muted-foreground";
  if (kind === "finished" || (kind === "notStarted" && document.chunkCount > 0)) detail = t("datasets.files.detail.chunks", { count: document.chunkCount });
  else if (kind === "failed") {
    detail = reason;
    detailClass = "line-clamp-2 break-words text-destructive";
  } else if (kind === "partial") {
    detail = document.run === "4" ? t("datasets.files.detail.partialFailed", { count: document.chunkCount, reason }) : t("datasets.files.detail.partialCancelled", { count: document.chunkCount });
    detailClass = "line-clamp-3 break-words text-muted-foreground";
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Badge variant={look.variant} data-testid="document-status" data-kind={kind}>
        {Icon === null ? null : <Icon className={`size-3 ${spin ?? ""}`.trim()} aria-hidden="true" />}
        {t(look.key)}
      </Badge>
      {detail === null ? null : (
        <p data-testid="document-status-detail" className={`text-xs font-normal ${detailClass}`}>
          {detail}
        </p>
      )}
      {kind === "finished" && skipped > 0 ? (
        <p data-testid="document-status-detail" className="flex items-start gap-1 text-xs font-normal text-foreground">
          <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>{t("datasets.files.detail.skipped", { skipped, total })}</span>
        </p>
      ) : null}
    </div>
  );
}
