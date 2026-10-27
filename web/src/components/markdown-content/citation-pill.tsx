import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReferenceChunk } from "@/services/chat-service";

export interface CitationPillProps {
  chunk: ReferenceChunk;
  open?: boolean;
  onOpenSource: (index: number, element: HTMLElement) => void;
}
export function CitationPill({ chunk, open = false, onOpenSource }: CitationPillProps) {
  const { t } = useTranslation();
  const number = chunk.index + 1;
  if (chunk.unavailable) return (
    <span data-testid="cite-pill-unavailable" data-cite-index={chunk.index} className="mx-1 inline-flex h-6 min-w-6 items-center justify-center gap-1 rounded border px-1 text-xs text-muted-foreground">
      <span aria-hidden="true">{number}</span><Lock aria-hidden="true" className="size-3" />
      <span className="sr-only">{t("chat.sources.unavailable", { n: number })}</span>
    </span>
  );
  return (
    <Button type="button" variant="outline" size="sm" data-testid="cite-pill" data-cite-index={chunk.index}
      aria-label={t("chat.sources.chip", { n: number, name: chunk.docName })} aria-pressed={open}
      className={cn("mx-1 inline-flex h-6 min-w-6 px-1 text-xs align-baseline [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11", open && "border-foreground")}
      onClick={(event) => onOpenSource(chunk.index, event.currentTarget)}>{number}</Button>
  );
}
