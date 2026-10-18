import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { useChunksRequest, type ChunkShow } from "@/hooks/use-chunk-request";
import type { ChunkView } from "@/services/chunk-service";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { chunkId, chunkRow, chunksOf, setChunks, type ChunkRow } from "@/test/server-areas/chunks";
import { waitUntil } from "@/test/wait-until";
import { ChunkList } from "./chunk-list";

useFilesServer();

const DOC = documentRow(1).id;
const CHUNKS_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}/chunks`;
const patchUrl = (n: number) => `${CHUNKS_URL}/${chunkId(n)}`;
const listCalls = () => server.callsTo("GET", CHUNKS_URL);
const lastParams = () => (listCalls().at(-1)?.params ?? {}) as Record<string, string | number>;

function many(count: number, over: (n: number) => Partial<ChunkRow> = () => ({})): ChunkRow[] {
  return Array.from({ length: count }, (_, i) => chunkRow(i + 1, over(i + 1)));
}

interface HostProps {
  canChange?: boolean;
  showPages?: boolean;
  start?: { page?: number; keywords?: string; show?: ChunkShow };
  onSelect?: (chunk: ChunkView, number: number, pageSizes: Record<string, [number, number]>, page?: number) => void;
}

function Host({ canChange = true, showPages = true, start = {}, onSelect = () => {} }: HostProps) {
  const [page, setPage] = useState(start.page ?? 1);
  const [keywords, setKeywords] = useState(start.keywords ?? "");
  const [show, setShow] = useState<ChunkShow>(start.show ?? "all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useChunksRequest({ datasetId: DATASET_ID, docId: DOC, page, keywords, show });
  return (
    <>
      <ChunkList
        query={query}
        page={page}
        keywords={keywords}
        show={show}
        canChange={canChange}
        showPages={showPages}
        selectedId={selectedId}
        datasetId={DATASET_ID}
        docId={DOC}
        onPage={setPage}
        onSearch={(next) => {
          setKeywords(next);
          setPage(1);
        }}
        onShow={(next) => {
          setShow(next);
          setPage(1);
        }}
        onClear={() => {
          setKeywords("");
          setShow("all");
          setPage(1);
        }}
        onSelect={(chunk, number, sizes, chip) => {
          setSelectedId(chunk.id);
          onSelect(chunk, number, sizes, chip);
        }}
      />
      <p data-testid="host-state">{`${page}|${keywords}|${show}`}</p>
      <Toaster />
    </>
  );
}

function renderList(props: HostProps = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Host {...props} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const cards = () => screen.queryAllByTestId("chunk-card");
const cardOf = (n: number) => document.querySelector<HTMLElement>(`[data-chunk-id="${chunkId(n)}"]`) as HTMLElement;
const state = () => screen.getByTestId("host-state").textContent;

describe("Chunk list and cards (UI-16, CHUNK-18)", () => {
  it("lists the first 20 chunks in an ordered list with their position, the count and a named pager", async () => {
    setChunks(server, DOC, many(25));
    renderList();
    const list = await screen.findByTestId("chunk-list");
    expect(list.tagName).toBe("OL");
    await waitFor(() => expect(cards()).toHaveLength(20));
    expect(within(cardOf(1)).getByTestId("chunk-select")).toHaveTextContent("Chunk 1 of 25");
    expect(within(cardOf(20)).getByTestId("chunk-select")).toHaveTextContent("Chunk 20 of 25");
    expect(screen.getByTestId("chunk-count")).toHaveTextContent("25 chunks");
    expect(screen.getByTestId("chunk-count")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("navigation", { name: "Chunk pages" })).toBeInTheDocument();
    expect(lastParams()).toMatchObject({ page: 1, size: 20 });
  });

  it("numbers the second page from 21 and says '1 chunk' in the singular", async () => {
    setChunks(server, DOC, many(21));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(within(cardOf(21)).getByTestId("chunk-select")).toHaveTextContent("Chunk 21 of 21");
  });

  it("shows the singular count", async () => {
    setChunks(server, DOC, many(1));
    renderList();
    expect(await screen.findByTestId("chunk-count")).toHaveTextContent("1 chunk");
  });

  it("carries id, origin and switch on the card and shows the badges for edited and hand-added chunks", async () => {
    setChunks(server, DOC, [chunkRow(1), chunkRow(2, { origin: "edited" }), chunkRow(3, { origin: "manual", positions: [] }), chunkRow(4, { enabled: false })]);
    renderList();
    await screen.findByTestId("chunk-list");
    expect(cardOf(1)).toHaveAttribute("data-origin", "parsed");
    expect(cardOf(1)).toHaveAttribute("data-enabled", "true");
    expect(within(cardOf(2)).getByTestId("chunk-badge-edited")).toHaveTextContent("Edited");
    expect(within(cardOf(3)).getByTestId("chunk-badge-manual")).toHaveTextContent("Added by hand");
    expect(within(cardOf(1)).queryByTestId("chunk-badge-edited")).toBeNull();
    expect(within(cardOf(4)).getByTestId("chunk-badge-off")).toHaveTextContent("Off");
    expect(cardOf(4)).toHaveAttribute("data-enabled", "false");
  });

  it("lists one page chip per page for a PDF and none when the format has no page geometry", async () => {
    const spans = chunkRow(1, { positions: [{ page: 2, x0: 1, x1: 5, top: 1, bottom: 5 }, { page: 3, x0: 1, x1: 5, top: 1, bottom: 5 }, { page: 2, x0: 1, x1: 9, top: 7, bottom: 9 }] });
    setChunks(server, DOC, [spans]);
    const view = renderList();
    await screen.findByTestId("chunk-list");
    const chips = within(cardOf(1)).getAllByTestId("chunk-page-chip");
    expect(chips.map((c) => c.textContent)).toEqual(["Page 2", "Page 3"]);
    view.unmount();
    renderList({ showPages: false });
    await screen.findByTestId("chunk-list");
    expect(screen.queryByTestId("chunk-page-chip")).toBeNull();
  });

  it("renders chunk text as a text node, clamps unselected text and shows a selected card in full", async () => {
    setChunks(server, DOC, [chunkRow(1, { text: '<img src=x onerror="alert(1)"><b>bold</b>\nsecond line' }), chunkRow(2)]);
    const user = userEvent.setup();
    renderList();
    const text = await within(await screen.findByTestId("chunk-list")).findAllByTestId("chunk-text");
    expect(text[0]?.textContent).toBe('<img src=x onerror="alert(1)"><b>bold</b>\nsecond line');
    expect(text[0]?.querySelector("*")).toBeNull();
    expect(text[0]?.className).toContain("whitespace-pre-wrap");
    expect(text[0]?.className).toContain("break-words");
    expect(text[0]?.className).toContain("line-clamp-6");
    await user.click(within(cardOf(1)).getByTestId("chunk-select"));
    expect(within(cardOf(1)).getByTestId("chunk-text").className).not.toContain("line-clamp-6");
    expect(within(cardOf(2)).getByTestId("chunk-text").className).toContain("line-clamp-6");
  });

  it("selects on a click anywhere on the card but not when text was selected, and reports the page sizes", async () => {
    setChunks(server, DOC, many(3));
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderList({ onSelect });
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(2)).getByTestId("chunk-text"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[0].id).toBe(chunkId(2));
    expect(onSelect.mock.calls[0]?.[1]).toBe(2);
    expect(onSelect.mock.calls[0]?.[2]).toEqual({ "1": [595, 842] });
    expect(within(cardOf(2)).getByTestId("chunk-select")).toHaveAttribute("aria-pressed", "true");
    expect(within(cardOf(1)).getByTestId("chunk-select")).toHaveAttribute("aria-pressed", "false");
    const selection = vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "some text" } as Selection);
    await user.click(within(cardOf(3)).getByTestId("chunk-text"));
    selection.mockRestore();
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("marks the selected card with an accent bar", async () => {
    setChunks(server, DOC, many(2));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    expect(within(cardOf(1)).queryByTestId("chunk-bar")).toBeNull();
    await user.click(within(cardOf(1)).getByTestId("chunk-select"));
    expect(within(cardOf(1)).getByTestId("chunk-bar")).toHaveAttribute("aria-hidden", "true");
  });

  it("selects the chunk and passes the page when a page chip is pressed", async () => {
    setChunks(server, DOC, [chunkRow(1, { positions: [{ page: 2, x0: 1, x1: 5, top: 1, bottom: 5 }, { page: 3, x0: 1, x1: 5, top: 1, bottom: 5 }] })]);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderList({ onSelect });
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(1)).getAllByTestId("chunk-page-chip")[1] as HTMLElement);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[3]).toBe(3);
  });

  it("moves the selection with the arrow keys, Home and End, and selects with Enter", async () => {
    setChunks(server, DOC, many(4));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    const header = (n: number) => within(cardOf(n)).getByTestId("chunk-select");
    header(1).focus();
    await user.keyboard("{ArrowDown}");
    expect(header(2)).toHaveFocus();
    expect(header(2)).toHaveAttribute("aria-pressed", "true");
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(header(4)).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(header(3)).toHaveFocus();
    await user.keyboard("{Home}");
    expect(header(1)).toHaveFocus();
    expect(header(1)).toHaveAttribute("aria-pressed", "true");
    await user.keyboard("{End}");
    expect(header(4)).toHaveFocus();
    expect(header(4)).toHaveAttribute("aria-pressed", "true");
    header(2).focus();
    await user.keyboard("{Enter}");
    expect(header(2)).toHaveAttribute("aria-pressed", "true");
    expect(header(4)).toHaveAttribute("aria-pressed", "false");
  });
});

describe("The chunk switch (CHUNK-21, D-12, D-26)", () => {
  it("is absent for a caller who may not change the document", async () => {
    setChunks(server, DOC, many(2));
    renderList({ canChange: false });
    await screen.findByTestId("chunk-list");
    expect(screen.queryByTestId("chunk-switch")).toBeNull();
    expect(screen.queryByTestId("chunk-edit")).toBeNull();
  });

  it("is named for the chunk, reads On or Off and shows the chunk's own setting", async () => {
    setChunks(server, DOC, [chunkRow(1), chunkRow(2, { enabled: false })]);
    renderList();
    await screen.findByTestId("chunk-list");
    const first = within(cardOf(1)).getByRole("switch", { name: "Include chunk 1 in search" });
    expect(first).toBeChecked();
    expect(within(cardOf(1)).getByTestId("chunk-switch")).toBe(first);
    expect(cardOf(1)).toHaveTextContent("On");
    expect(within(cardOf(2)).getByRole("switch", { name: "Include chunk 2 in search" })).not.toBeChecked();
  });

  it("is not optimistic: it stays busy and unchanged until the server answers, ignores presses meanwhile, then shows the server's value", async () => {
    setChunks(server, DOC, many(3));
    let release!: () => void;
    server.holds[`PATCH ${patchUrl(2)}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    const toggle = within(cardOf(2)).getByTestId("chunk-switch");
    await user.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-busy", "true"));
    expect(toggle).toBeChecked();
    await user.click(toggle);
    expect(server.callsTo("PATCH", patchUrl(2))).toHaveLength(1);
    expect(JSON.parse(String(server.callsTo("PATCH", patchUrl(2))[0]?.data))).toEqual({ available: false });
    release();
    await waitFor(() => expect(within(cardOf(2)).getByTestId("chunk-switch")).not.toBeChecked());
    expect(within(cardOf(2)).getByTestId("chunk-switch")).not.toHaveAttribute("aria-busy");
  });

  it("leaves a switched-off chunk in its place, dimmed, dashed and badged, and brings it back with its own switch", async () => {
    setChunks(server, DOC, many(3));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(2)).getByTestId("chunk-switch"));
    await waitFor(() => expect(cardOf(2)).toHaveAttribute("data-enabled", "false"));
    expect(cards().map((c) => c.getAttribute("data-chunk-id"))).toEqual([chunkId(1), chunkId(2), chunkId(3)]);
    expect(within(cardOf(2)).getByTestId("chunk-badge-off")).toBeInTheDocument();
    expect(cardOf(2).querySelector('[data-testid="chunk-text"]')?.className).toContain("text-muted-foreground");
    expect(cardOf(2).innerHTML).toContain("border-dashed");
    await user.click(within(cardOf(2)).getByTestId("chunk-switch"));
    await waitFor(() => expect(cardOf(2)).toHaveAttribute("data-enabled", "true"));
    expect(within(cardOf(2)).queryByTestId("chunk-badge-off")).toBeNull();
    expect(chunksOf(server, DOC)[1]?.enabled).toBe(true);
  });

  it("keeps the previous value and says so when the server refuses", async () => {
    setChunks(server, DOC, many(2));
    server.forced[`PATCH ${patchUrl(1)}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(1)).getByTestId("chunk-switch"));
    expect(await screen.findByText("The chunk's search setting wasn't changed. Try again.")).toBeInTheDocument();
    expect(within(cardOf(1)).getByTestId("chunk-switch")).toBeChecked();
    expect(within(cardOf(1)).getByTestId("chunk-switch")).not.toHaveAttribute("aria-busy");
  });

  it("under the On filter lets the chunk leave after the refetch, announces it and moves focus to the next card's switch", async () => {
    setChunks(server, DOC, many(3));
    const user = userEvent.setup();
    renderList({ start: { show: "on" } });
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(1)).getByTestId("chunk-switch"));
    await waitFor(() => expect(cardOf(1)).toBeNull());
    expect(screen.getByTestId("chunk-switch-live")).toHaveTextContent("Chunk switched off. It is now listed under Off.");
    await waitFor(() => expect(within(cardOf(2)).getByTestId("chunk-switch")).toHaveFocus());
    expect(cards()).toHaveLength(2);
  });

  it("announces the reverse under the Off filter", async () => {
    setChunks(server, DOC, [chunkRow(1, { enabled: false }), chunkRow(2, { enabled: false })]);
    const user = userEvent.setup();
    renderList({ start: { show: "off" } });
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(2)).getByTestId("chunk-switch"));
    await waitFor(() => expect(cardOf(2)).toBeNull());
    expect(screen.getByTestId("chunk-switch-live")).toHaveTextContent("Chunk switched on. It is now listed under On.");
    await waitFor(() => expect(within(cardOf(1)).getByTestId("chunk-switch")).toHaveFocus());
  });

  it("moves focus to the filter when the list becomes empty", async () => {
    setChunks(server, DOC, many(1));
    const user = userEvent.setup();
    renderList({ start: { show: "on" } });
    await screen.findByTestId("chunk-list");
    await user.click(within(cardOf(1)).getByTestId("chunk-switch"));
    await waitFor(() => expect(screen.getByTestId("chunk-filter").contains(document.activeElement)).toBe(true));
    expect(await screen.findByText("No chunks match")).toBeInTheDocument();
  });
});

describe("Search, filter and paging (D-12, FE-01)", () => {
  it("debounces typing into one request with the keywords and returns to page 1", async () => {
    setChunks(server, DOC, many(25, (n) => ({ text: n === 22 ? "needle in a haystack" : `plain text ${n}` })));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitUntil(() => state() === "2||all");
    const before = listCalls().length;
    await user.type(screen.getByRole("searchbox", { name: "Search in chunks" }), "needle");
    expect(listCalls().length).toBe(before);
    await waitUntil(() => state() === "1|needle|all", { describe: "debounced keywords" });
    await waitUntil(() => cards().length === 1);
    expect(listCalls().length).toBe(before + 1);
    expect(lastParams()).toMatchObject({ keywords: "needle", page: 1 });
    expect(screen.getByTestId("chunk-search")).toBeInTheDocument();
  });

  it("filters All, On and Off through a named group and sends the available flag", async () => {
    setChunks(server, DOC, [chunkRow(1), chunkRow(2, { enabled: false }), chunkRow(3)]);
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    const group = screen.getByRole("group", { name: "Show" });
    expect(group).toBe(screen.getByTestId("chunk-filter"));
    expect(screen.getByTestId("chunk-filter-all")).toBeChecked();
    await user.click(within(group).getByText("Off"));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(lastParams().available).toBe(0);
    expect(screen.getByTestId("chunk-count")).toHaveTextContent("1 chunk");
    await user.click(within(group).getByText("On"));
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(lastParams().available).toBe(1);
    await user.click(within(group).getByText("All"));
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(lastParams().available).toBeUndefined();
  });

  it("keeps the cards, the toolbar and the focus while the next page loads", async () => {
    setChunks(server, DOC, many(25));
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId("chunk-list");
    await waitFor(() => expect(cards()).toHaveLength(20));
    let release!: () => void;
    server.holds[`GET ${CHUNKS_URL}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    const next = screen.getByRole("button", { name: "Next" });
    next.focus();
    await user.keyboard("{Enter}");
    await waitUntil(() => state() === "2||all");
    expect(cards()).toHaveLength(20);
    expect(screen.getByTestId("chunk-search")).toBeInTheDocument();
    expect(document.activeElement?.closest("nav")).toHaveAccessibleName("Chunk pages");
    release();
    await waitFor(() => expect(cards()).toHaveLength(5));
    expect(document.activeElement?.closest("nav")).toHaveAccessibleName("Chunk pages");
  });

  it("shows five card skeletons while the first page loads", async () => {
    setChunks(server, DOC, many(3));
    let release!: () => void;
    server.holds[`GET ${CHUNKS_URL}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderList();
    expect(await screen.findAllByTestId("chunk-card-skeleton")).toHaveLength(5);
    release();
    await screen.findByTestId("chunk-list");
    expect(screen.queryAllByTestId("chunk-card-skeleton")).toHaveLength(0);
  });
});

describe("List states (UI-SPEC States)", () => {
  it("says no chunks match and clears search and filter from 'Show all chunks'", async () => {
    setChunks(server, DOC, many(3));
    const user = userEvent.setup();
    renderList({ start: { keywords: "zzz", show: "on" } });
    expect(await screen.findByRole("heading", { name: "No chunks match" })).toBeInTheDocument();
    expect(screen.getByText("Try other words, or show all chunks.")).toBeInTheDocument();
    expect(screen.getByTestId("chunk-search")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all chunks" }));
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(state()).toBe("1||all");
  });

  it("says none are switched off under the Off filter", async () => {
    setChunks(server, DOC, many(3));
    const user = userEvent.setup();
    renderList({ start: { show: "off" } });
    expect(await screen.findByRole("heading", { name: "No chunks are switched off" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all chunks" }));
    await waitFor(() => expect(cards()).toHaveLength(3));
  });

  it("keeps search, filter and pager mounted around a list error and retries", async () => {
    setChunks(server, DOC, many(3));
    server.forced[`GET ${CHUNKS_URL}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByRole("heading", { name: "Couldn't load chunks" })).toBeInTheDocument();
    expect(screen.getByTestId("chunk-search")).toBeInTheDocument();
    expect(screen.getByTestId("chunk-filter")).toBeInTheDocument();
    delete server.forced[`GET ${CHUNKS_URL}`];
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(cards()).toHaveLength(3));
  });
});
