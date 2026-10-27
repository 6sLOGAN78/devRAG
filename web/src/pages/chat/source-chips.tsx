import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { ReferenceChunk } from "@/services/chat-service";

export function SourceChips({ chunks, onOpen, openIndex }: { chunks: ReferenceChunk[]; onOpen: (index: number, trigger: HTMLElement) => void; openIndex?: number | null }) {
  const { t } = useTranslation();
  const visible = [...new Map(chunks.filter((chunk) => !chunk.unavailable).map((chunk) => [chunk.index, chunk])).values()].sort((a, b) => a.index - b.index);
  if (!visible.length) return null;
  return <div data-testid="source-chips" className="grid gap-1"><p className="text-xs font-semibold">{t("chat.sources.heading")}</p><div className="flex flex-wrap gap-2">
    {visible.map((chunk) => !chunk.unavailable ? <Button key={chunk.index} type="button" variant="outline" data-testid="source-chip" data-cite-index={chunk.index} aria-pressed={openIndex === chunk.index} aria-label={t("chat.sources.chip", { n: chunk.index + 1, name: chunk.docName })}
      className={`h-10 max-w-full gap-2 [@media(pointer:coarse)]:h-11 ${openIndex === chunk.index ? "border-foreground" : ""}`} onClick={(event) => onOpen(chunk.index, event.currentTarget)}>
      <span className="text-xs tabular-nums">{chunk.index + 1}</span><span className="max-w-[20ch] truncate">{chunk.docName}</span>{/\.pdf$/i.test(chunk.docName) && chunk.positions[0]?.page ? <span className="text-xs">{t("chat.sources.page", { page: chunk.positions[0].page })}</span> : null}
    </Button> : null)}
  </div></div>;
}
