import type { UseQueryResult } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type MutableRefObject, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { CHUNKS_PAGE_SIZE, useUpdateChunkRequest, type ChunkShow } from "@/hooks/use-chunk-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { ChunkPage, ChunkView } from "@/services/chunk-service";
import { notifyError } from "@/services/notify";
import { chunkFailureOf } from "../dataset/errors";
import { ChunkCard } from "./chunk-card";
import { ChunkEditor } from "./chunk-editor";
import { ChunkListError, ChunkListSkeleton, NoChunks } from "./inspector-states";

/** Longest search the page keeps in its address. */
export const MAX_KEYWORDS = 100;

const SHOWS: readonly ChunkShow[] = ["all", "on", "off"];
const HEADER = '[data-testid="chunk-select"]';

/** What the one open editor is for: a chunk as it was stored when the editor opened, or a new chunk. */
export type Editing = { kind: "edit"; chunk: ChunkView; number: number } | { kind: "add" };

export interface ChunkListProps {
  query: Pick<UseQueryResult<ChunkPage>, "data" | "isPending" | "isError" | "refetch">;
  datasetId: string;
  docId: string;
  page: number;
  keywords: string;
  show: ChunkShow;
  /** The caller may change the document and it is not parsing: the switch is drawn. */
  canChange: boolean;
  /** PDF: cards list their pages. */
  showPages: boolean;
  selectedId: string | null;
  onPage: (page: number, options?: { replace?: boolean }) => void;
  onSearch: (keywords: string) => void;
  onShow: (show: ChunkShow) => void;
  /** Clears search and filter. */
  onClear: () => void;
  /** A chunk was selected; `chipPage` is the page whose chip was pressed. */
  onSelect: (chunk: ChunkView, number: number, pageSizes: Record<string, [number, number]>, chipPage?: number) => void;
  /** The open editor, if any. */
  editing: Editing | null;
  /** Runs a leaving action now, or holds it behind the Discard dialog while the editor holds changed text. */
  guard: (action: () => void) => void;
  onEdit: (chunk: ChunkView, number: number) => void;
  onAdd: () => void;
  onEditorDirty: (dirty: boolean) => void;
  /** The editor was discarded. */
  onEditorClose: () => void;
  /** The write succeeded. */
  onEditorSaved: (chunk: ChunkView) => void;
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>;
  /** The id of a chunk just added: it is selected and its header focused as soon as the list shows it. */
  newId: string | null;
  onNewShown: () => void;
}

/** Where focus goes once the editor has closed. */
type Restore = { kind: "edit"; id: string } | { kind: "add" };

interface FocusPlan {
  id: string;
  /** The card to move to when the chunk has left: the one after it, else the one before. */
  next: string | null;
}

/**
 * The search, the filter, the cards and the pager of the inspector (UI-16). The query belongs to the page; this part
 * owns the chunk switch: it is not optimistic, so a card shows the server's value, and under the On or Off filter the
 * chunk leaves after the refetch with a polite announcement and a place for focus to go (D-12, D-26).
 */
export function ChunkList({ query, datasetId, docId, page, keywords, show, canChange, showPages, selectedId, onPage, onSearch, onShow, onClear, onSelect, editing, guard, onEdit, onAdd, onEditorDirty, onEditorClose, onEditorSaved, textareaRef, newId, onNewShown }: ChunkListProps) {
  const { t } = useTranslation();
  const update = useUpdateChunkRequest();
  const workspaceName = useWorkspaceName(useActiveWorkspace()?.tenantId ?? "");
  const listRef = useRef<HTMLOListElement | null>(null);
  const filterRef = useRef<HTMLDivElement | null>(null);
  const addRef = useRef<HTMLButtonElement | null>(null);
  const restore = useRef<Restore | null>(null);
  const claimed = useRef<Set<string>>(new Set());
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [live, setLive] = useState("");
  const [plan, setPlan] = useState<FocusPlan | null>(null);

  const data = query.data;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / CHUNKS_PAGE_SIZE));
  const pastEnd = data !== undefined && items.length === 0 && total > 0 && page > pages;
  const filtered = keywords !== "" || show !== "all";

  useEffect(() => {
    if (pastEnd) onPage(pages, { replace: true });
  }, [pastEnd, pages, onPage]);

  // The plan belongs to the list as it was shown; another page, search or filter drops it.
  useEffect(() => setPlan(null), [page, keywords, show]);

  // After a chunk left the list, focus goes to the next card's switch, or to the filter when nothing is left. The plan
  // waits while the chunk is still listed: the refetch that removes it arrives after the switch has answered.
  useEffect(() => {
    if (plan === null || items.some((item) => item.id === plan.id)) return;
    setPlan(null);
    const target = plan.next === null ? null : listRef.current?.querySelector<HTMLElement>(`[data-chunk-id="${plan.next}"] [data-testid="chunk-switch"]`);
    (target ?? filterRef.current?.querySelector<HTMLElement>("input:checked"))?.focus();
  }, [plan, items]);

  // A chunk just added is selected and its header focused once the list holds it.
  useEffect(() => {
    if (newId === null) return;
    const index = items.findIndex((item) => item.id === newId);
    const chunk = items[index];
    if (chunk === undefined) return;
    onNewShown();
    select(chunk, index);
    listRef.current?.querySelector<HTMLElement>(`[data-chunk-id="${newId}"] ${HEADER}`)?.focus();
  }, [newId, items]);

  // After the editor closed, focus goes back to the control that opened it.
  useEffect(() => {
    if (editing !== null || restore.current === null) return;
    const target = restore.current;
    restore.current = null;
    const element = target.kind === "add" ? addRef.current : listRef.current?.querySelector<HTMLElement>(`[data-chunk-id="${target.id}"] [data-testid="chunk-edit"]`);
    element?.focus();
  }, [editing, items]);

  function close(kind: Restore): void {
    restore.current = kind;
    onEditorClose();
  }

  function saved(kind: Restore, chunk: ChunkView): void {
    restore.current = kind.kind === "add" ? null : kind;
    onEditorSaved(chunk);
  }

  function editorOf(shown: Editing): ReactNode {
    const kind: Restore = shown.kind === "add" ? { kind: "add" } : { kind: "edit", id: shown.chunk.id };
    return (
      <ChunkEditor
        key={shown.kind === "add" ? "new" : shown.chunk.id}
        mode={shown.kind}
        datasetId={datasetId}
        docId={docId}
        chunk={shown.kind === "edit" ? shown.chunk : undefined}
        textareaRef={textareaRef}
        guard={guard}
        onDirtyChange={onEditorDirty}
        onClose={() => close(kind)}
        onSaved={(chunk) => saved(kind, chunk)}
      />
    );
  }

  function select(chunk: ChunkView, index: number, chipPage?: number): void {
    onSelect(chunk, (page - 1) * CHUNKS_PAGE_SIZE + index + 1, data?.pageSizes ?? {}, chipPage);
  }

  function release(id: string): void {
    claimed.current.delete(id);
    setBusy(new Set(claimed.current));
  }

  async function toggle(chunk: ChunkView, index: number): Promise<void> {
    if (claimed.current.has(chunk.id)) return;
    claimed.current.add(chunk.id);
    setBusy(new Set(claimed.current));
    const enabled = !chunk.enabled;
    try {
      await update.mutateAsync({ datasetId, docId, chunkId: chunk.id, changes: { enabled } });
      if (show !== "all") {
        setLive(enabled ? t("inspector.live.switchedOn") : t("inspector.live.switchedOff"));
        setPlan({ id: chunk.id, next: items[index + 1]?.id ?? items[index - 1]?.id ?? null });
      }
    } catch (error) {
      const placed = chunkFailureOf(error, "switch");
      if (placed.key !== null) notifyError({ id: "chunk-switch", title: t(placed.key, { workspace: workspaceName }), description: "" });
    } finally {
      release(chunk.id);
    }
  }

  function navigate(event: KeyboardEvent<HTMLOListElement>): void {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key) || !(event.target instanceof Element) || !event.target.matches(HEADER)) return;
    const headers = Array.from(listRef.current?.querySelectorAll<HTMLElement>(HEADER) ?? []);
    const at = headers.indexOf(event.target as HTMLElement);
    if (at < 0 || headers.length === 0) return;
    let to = at;
    if (event.key === "ArrowDown") to = Math.min(headers.length - 1, at + 1);
    else if (event.key === "ArrowUp") to = Math.max(0, at - 1);
    else if (event.key === "Home") to = 0;
    else to = headers.length - 1;
    event.preventDefault();
    const chunk = items[to];
    if (chunk !== undefined) select(chunk, to);
    headers[to]?.focus();
  }

  const editingId = editing?.kind === "edit" ? editing.chunk.id : null;
  // The chunk being edited may be gone from the list after a refetch (it was deleted); its editor stays so the text is not lost.
  const orphan = editing?.kind === "edit" && !items.some((item) => item.id === editing.chunk.id) ? editing : null;

  let body;
  if (data === undefined && query.isError) body = <ChunkListError onRetry={() => void query.refetch()} />;
  else if (data === undefined || query.isPending || pastEnd) body = <ChunkListSkeleton />;
  else {
    const none = items.length === 0 && filtered ? <NoChunks kind={show === "off" && keywords === "" ? "noneOff" : "noMatch"} onClear={onClear} /> : null;
    body =
      items.length === 0 && editing === null ? (
        none
      ) : (
        <>
          <ol ref={listRef} data-testid="chunk-list" className="flex flex-col gap-3" onKeyDown={navigate}>
            {editing?.kind === "add" ? (
              <li data-testid="chunk-new">
                <Card className="p-4">{editorOf(editing)}</Card>
              </li>
            ) : null}
            {(orphan === null ? items : [orphan.chunk, ...items]).map((chunk, at) => {
              const gone = orphan !== null && at === 0;
              const index = orphan === null ? at : at - 1;
              const number = gone ? orphan.number : (page - 1) * CHUNKS_PAGE_SIZE + index + 1;
              return (
                <ChunkCard
                  key={chunk.id}
                  chunk={chunk}
                  number={number}
                  total={total}
                  selected={!gone && chunk.id === selectedId}
                  showPages={showPages}
                  canChange={canChange}
                  busy={busy.has(chunk.id)}
                  onSelect={() => !gone && select(chunk, index)}
                  onChip={(chipPage) => !gone && select(chunk, index, chipPage)}
                  onToggle={() => !gone && void toggle(chunk, index)}
                  onEdit={() => guard(() => onEdit(chunk, number))}
                  editor={chunk.id === editingId && editing?.kind === "edit" ? editorOf(editing) : undefined}
                />
              );
            })}
          </ol>
          {none}
        </>
      );
  }

  return (
    <div data-testid="chunk-list-region" className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div data-testid="chunk-search" className="min-w-48 flex-1">
          <SearchInput value={keywords} onSearch={(next) => onSearch(next.slice(0, MAX_KEYWORDS))} label={t("inspector.list.search")} clearLabel={t("common.search.clear")} />
        </div>
        <div ref={filterRef}>
          <SegmentedControl
            legend={t("inspector.list.show")}
            name="chunk-show"
            testId="chunk-filter"
            value={show}
            onChange={(next) => onShow(SHOWS.find((option) => option === next) ?? "all")}
            options={SHOWS.map((option) => ({ value: option, label: t(`inspector.list.${option}`) }))}
          />
        </div>
        {canChange ? (
          <Button
            ref={addRef}
            type="button"
            variant="outline"
            data-testid="chunk-add"
            onClick={() => {
              if (editing?.kind === "add") textareaRef.current?.focus();
              else guard(onAdd);
            }}
          >
            <Plus aria-hidden="true" />
            {t("inspector.list.add")}
          </Button>
        ) : null}
        <p data-testid="chunk-count" aria-live="polite" className="text-xs font-normal text-muted-foreground">
          {data === undefined ? "" : t("inspector.list.count", { count: total })}
        </p>
      </div>
      <p data-testid="chunk-switch-live" role="status" className="sr-only">
        {live}
      </p>
      {body}
      {data !== undefined && !pastEnd && items.length > 0 ? (
        <Pagination
          aria-label={t("inspector.list.pages")}
          page={page}
          pages={pages}
          onPageChange={onPage}
          previousLabel={t("common.pagination.previous")}
          nextLabel={t("common.pagination.next")}
          statusLabel={t("common.pagination.status", { page, pages })}
        />
      ) : null}
    </div>
  );
}
