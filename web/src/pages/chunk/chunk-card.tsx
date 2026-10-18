import { EyeOff, Pencil, PenLine } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { ChunkView } from "@/services/chunk-service";

export interface ChunkCardProps {
  chunk: ChunkView;
  /** Position of the chunk in the current result, and the size of the result. */
  number: number;
  total: number;
  selected: boolean;
  /** PDF only: one chip per page the chunk lies on. */
  showPages: boolean;
  /** The caller may change the document and it is not parsing: the switch is drawn. */
  canChange: boolean;
  /** The switch is waiting for the server. */
  busy: boolean;
  onSelect: () => void;
  onChip: (page: number) => void;
  onToggle: () => void;
  /** Present when the caller may edit this chunk: the pencil button. */
  onEdit?: () => void;
  /** The open editor of this chunk. It replaces the text, and the switch and the pencil are not drawn while it is there. */
  editor?: ReactNode;
}

/** The pages a chunk lies on, each once, in order. */
export function pagesOf(chunk: Pick<ChunkView, "positions">): number[] {
  return Array.from(new Set(chunk.positions.map((position) => position.page))).sort((a, b) => a - b);
}

const INTERACTIVE = "button, a, input, label, textarea, select";

/**
 * One chunk of the inspector list. Clicking anywhere on the card selects it, unless the click was on a control or the
 * reader has selected text to copy. The text is a text node: nothing in a chunk is ever interpreted as markup.
 */
export function ChunkCard({ chunk, number, total, selected, showPages, canChange, busy, onSelect, onChip, onToggle, onEdit, editor }: ChunkCardProps) {
  const { t } = useTranslation();
  const off = !chunk.enabled;
  const pages = showPages ? pagesOf(chunk) : [];

  function click(event: MouseEvent<HTMLDivElement>): void {
    if (event.target instanceof Element && event.target.closest(INTERACTIVE) !== null) return;
    if ((window.getSelection?.()?.toString() ?? "") !== "") return;
    onSelect();
  }

  return (
    <li data-testid="chunk-card" data-chunk-id={chunk.id} data-origin={chunk.origin} data-enabled={chunk.enabled ? "true" : "false"}>
      <Card className={cn("relative flex flex-col gap-2 overflow-hidden p-4", off && "border-dashed")} onClick={click}>
        {selected ? <span data-testid="chunk-bar" aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-primary" /> : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="ghost" size="sm" data-testid="chunk-select" aria-pressed={selected} onClick={onSelect}>
            {t("inspector.card.select", { n: number, total })}
          </Button>
          {pages.map((page) => (
            <button
              key={page}
              type="button"
              data-testid="chunk-page-chip"
              className={cn(badgeVariants({ variant: "outline" }), "cursor-pointer hover:bg-muted")}
              onClick={() => onChip(page)}
            >
              {t("inspector.card.page", { page })}
            </button>
          ))}
          {chunk.origin === "edited" ? (
            <Badge variant="outline" data-testid="chunk-badge-edited">
              <Pencil className="size-3" aria-hidden="true" />
              {t("inspector.card.edited")}
            </Badge>
          ) : null}
          {chunk.origin === "manual" ? (
            <Badge variant="outline" data-testid="chunk-badge-manual">
              <PenLine className="size-3" aria-hidden="true" />
              {t("inspector.card.manual")}
            </Badge>
          ) : null}
          {off ? (
            <Badge variant="default" data-testid="chunk-badge-off">
              <EyeOff className="size-3" aria-hidden="true" />
              {t("inspector.list.off")}
            </Badge>
          ) : null}
          {canChange && editor === undefined ? (
            <div className="ml-auto flex items-center gap-2">
              {onEdit !== undefined ? (
                <Button type="button" variant="ghost" size="icon" data-testid="chunk-edit" aria-label={t("inspector.card.editLabel", { n: number })} onClick={onEdit}>
                  <Pencil aria-hidden="true" />
                </Button>
              ) : null}
              <Switch
                checked={chunk.enabled}
                busy={busy}
                onChange={onToggle}
                onLabel={t("inspector.list.on")}
                offLabel={t("inspector.list.off")}
                aria-label={t("inspector.card.switchLabel", { n: number })}
                data-testid="chunk-switch"
              />
            </div>
          ) : null}
        </div>
        {editor !== undefined ? (
          editor
        ) : (
          <p data-testid="chunk-text" className={cn("whitespace-pre-wrap break-words text-sm font-normal", !selected && "line-clamp-6", off && "text-muted-foreground")}>
            {chunk.text}
          </p>
        )}
      </Card>
    </li>
  );
}
