import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { CHUNK_ROUTE, chunkPath, datasetFilesPath, documentViewerPath } from "@/constants/app-paths";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DATASET_ID, datasetRow, documentRow, membershipRow, storedMemberships, type DocumentRow } from "@/test/dataset-server";
import { OWNER, actAs, server, useFilesServer } from "@/test/files-harness";
import { chunkId, chunkRow, setChunks, type ChunkRow } from "@/test/server-areas/chunks";
import { addFileLog, advanceParse, setFileExtra } from "@/test/server-areas/files";
import { waitUntil } from "@/test/wait-until";
import ChunkInspector from ".";

useFilesServer();

/** Document ids are 32 lowercase hex characters; the shared fixture ids are not, so the first document gets its own. */
const DOC = "d".repeat(31) + "1";
const firstDoc = (over: Partial<DocumentRow> = {}): DocumentRow => documentRow(1, { id: DOC, ...over });
const CHUNKS_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}/chunks`;
const DETAIL_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}`;
const MEMBER: SessionUser = { ...OWNER, id: "u4", nickname: "Dan", tenantId: "t4", tenantName: "Dan's workspace" };
let router: ReturnType<typeof createMemoryRouter>;

const location = () => `${router.state.location.pathname}${router.state.location.search}`;
const listCalls = () => server.callsTo("GET", CHUNKS_URL);
const cards = () => screen.queryAllByTestId("chunk-card");
const cardOf = (n: number) => document.querySelector<HTMLElement>(`[data-chunk-id="${chunkId(n)}"]`) as HTMLElement;

function renderPage(entry = chunkPath(DATASET_ID, DOC)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  router = createMemoryRouter(
    [
      { path: CHUNK_ROUTE, element: <ChunkInspector /> },
      { path: "/dataset/files", element: <p data-testid="files-page">files</p> },
      { path: "/datasets", element: <p data-testid="gallery-page">gallery</p> },
      { path: "/document", element: <p data-testid="viewer-page">viewer</p> },
    ],
    { initialEntries: [entry] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
}

function pdf(pages = 13): void {
  setFileExtra(server, DOC, { preview: "pages", pagesTotal: pages });
  server.documents[DATASET_ID] = (server.documents[DATASET_ID] ?? []).map((d) => (d.id === DOC ? { ...d, run: "3" } : d));
}
function finished(count: number, over: (n: number) => Partial<ChunkRow> = () => ({})): void {
  const rows = Array.from({ length: count }, (_, i) => chunkRow(i + 1, over(i + 1)));
  setChunks(server, DOC, rows);
  server.documents[DATASET_ID] = (server.documents[DATASET_ID] ?? []).map((d) => (d.id === DOC ? { ...d, run: "3", chunk_num: count } : d));
}

beforeEach(() => {
  server.documents[DATASET_ID] = [firstDoc({ run: "3", chunk_num: 3 }), documentRow(2), documentRow(3)];
});

describe("Structure (UI-16)", () => {
  it("shows the back link, the document name, the meta line, and the chunks", async () => {
    finished(3);
    renderPage();
    const page = await screen.findByTestId("chunk-page");
    expect(await within(page).findByTestId("chunk-back")).toHaveAttribute("href", datasetFilesPath(DATASET_ID));
    expect(screen.getByTestId("chunk-back")).toHaveTextContent("Reports");
    const title = within(page).getByRole("heading", { level: 1, name: "report-01.pdf" });
    expect(title).toHaveAttribute("title", "report-01.pdf");
    expect(title.className).toContain("break-all");
    const meta = await screen.findByTestId("chunk-meta");
    expect(within(meta).getByTestId("document-status")).toHaveTextContent("Finished");
    expect(meta).toHaveTextContent("3 chunks");
    expect(meta).toHaveTextContent("Method: General");
    expect(within(meta).getByTestId("chunk-open-document")).toHaveAttribute("href", documentViewerPath(DATASET_ID, DOC));
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(document.title).toBe("Chunks of report-01.pdf - devRag");
  });

  it("puts nothing about the selection in the address", async () => {
    finished(3);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(3));
    const before = location();
    await user.click(within(cardOf(2)).getByTestId("chunk-select"));
    expect(within(cardOf(2)).getByTestId("chunk-select")).toHaveAttribute("aria-pressed", "true");
    expect(location()).toBe(before);
  });

  it("renders hostile chunk text as text and never creates an element", async () => {
    finished(1, () => ({ text: '<script>alert(1)</script><img src=x onerror="alert(2)"><iframe src="http://evil.test"></iframe>' }));
    renderPage();
    const text = await screen.findByTestId("chunk-text");
    expect(text.querySelector("*")).toBeNull();
    expect(document.querySelector("iframe, script, img[onerror]")).toBeNull();
    expect(text.textContent).toContain("<script>alert(1)</script>");
  });

  it("opens the document through a link to the viewer", async () => {
    finished(1);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByTestId("chunk-open-document"));
    expect(await screen.findByTestId("viewer-page")).toBeInTheDocument();
  });
});

describe("Document not found and errors", () => {
  it("answers a malformed dataset or document id with one block and no request", async () => {
    renderPage(`${CHUNK_ROUTE}?id=zzz&doc=${DOC}`);
    const block = await screen.findByTestId("chunk-not-found");
    expect(block).toHaveTextContent("Document not found");
    expect(screen.queryByTestId("chunk-back")).toBeNull();
    expect(screen.queryByTestId("chunk-meta")).toBeNull();
    expect(server.calls.filter((c) => /datasets/.test(c.url ?? ""))).toHaveLength(0);
  });

  it("answers a malformed document id the same way, without asking for the document", async () => {
    renderPage(`${CHUNK_ROUTE}?id=${DATASET_ID}&doc=UPPER`);
    expect(await screen.findByTestId("chunk-not-found")).toBeInTheDocument();
    expect(server.calls.filter((c) => /documents/.test(c.url ?? ""))).toHaveLength(0);
    expect(listCalls()).toHaveLength(0);
  });

  it("shows the same block when the server says the document does not exist", async () => {
    renderPage(chunkPath(DATASET_ID, "b".repeat(32)));
    const block = await screen.findByTestId("chunk-not-found");
    expect(block).toHaveTextContent("It may have been deleted, or it isn't shared with you.");
    expect(within(block).getByRole("link", { name: "Back to datasets" })).toBeInTheDocument();
  });

  it("shows the same block when the dataset does not exist", async () => {
    renderPage(chunkPath("c".repeat(32), DOC));
    expect(await screen.findByTestId("chunk-not-found")).toBeInTheDocument();
  });

  it("offers a retry when the document cannot be loaded for another reason", async () => {
    server.forced[`GET ${DETAIL_URL}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Couldn't load this document" })).toBeInTheDocument();
    delete server.forced[`GET ${DETAIL_URL}`];
    finished(2);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(cards()).toHaveLength(2));
  });
});

describe("The page preview beside the chunks (UI-16, CHUNK-18)", () => {
  it("shows a pane for a PDF and no pane or chips for a format without page geometry", async () => {
    pdf(13);
    finished(2);
    renderPage();
    expect(await screen.findByTestId("page-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("no-preview-note")).toBeNull();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(within(cardOf(1)).getAllByTestId("chunk-page-chip")).toHaveLength(1);
  });

  it("shows only the list and the one-line note for a DOCX", async () => {
    server.documents[DATASET_ID] = [firstDoc({ run: "3", chunk_num: 2, name: "notes.docx", suffix: "docx", type: "doc" })];
    setChunks(server, DOC, [chunkRow(1, { positions: [] }), chunkRow(2, { positions: [] })]);
    renderPage();
    expect(await screen.findByTestId("no-preview-note")).toHaveTextContent("DOCX files have no page preview. Chunks are shown as the text that was read from the file.");
    expect(screen.queryByTestId("page-preview")).toBeNull();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.queryByTestId("chunk-page-chip")).toBeNull();
    expect(screen.getByTestId("chunk-list-column").className).toContain("max-w-3xl");
  });

  it("shows no pane for a PDF whose page count is not known", async () => {
    setFileExtra(server, DOC, { preview: "pages", pagesTotal: null });
    finished(1);
    renderPage();
    expect(await screen.findByTestId("no-preview-note")).toBeInTheDocument();
    expect(screen.queryByTestId("page-preview")).toBeNull();
  });

  it("shows the first chunk's box on page 13 of a 13-page document, inside the image wrapper, when it is selected", async () => {
    pdf(13);
    finished(3, (n) => (n === 1 ? { positions: [{ page: 13, x0: 59.5, top: 84.2, x1: 297.5, bottom: 168.4 }] } : {}));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 1 of 13");
    await user.click(within(cardOf(1)).getByTestId("chunk-select"));
    await waitFor(() => expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 13 of 13"));
    const box = await screen.findByTestId("preview-box");
    expect(screen.getByTestId("preview-scroll").firstElementChild).toContainElement(box);
    expect(box.style.left).toBe("10%");
    expect(box.style.top).toBe("10%");
    expect(server.calls.some((c) => /pages\/13\/image$/.test(c.url ?? ""))).toBe(true);
  });

  it("changes the image when a chunk on another page is selected and when a page chip is pressed", async () => {
    pdf(13);
    finished(2, (n) => ({ positions: n === 1 ? [{ page: 2, x0: 1, x1: 50, top: 1, bottom: 50 }, { page: 4, x0: 1, x1: 50, top: 1, bottom: 50 }] : [{ page: 5, x0: 1, x1: 50, top: 1, bottom: 50 }] }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(2));
    await user.click(within(cardOf(2)).getByTestId("chunk-select"));
    await waitFor(() => expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 5 of 13"));
    await user.click(within(cardOf(1)).getAllByTestId("chunk-page-chip")[1] as HTMLElement);
    await waitFor(() => expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 4 of 13"));
    expect(within(cardOf(1)).getByTestId("chunk-select")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByTestId("preview-box")).toBeInTheDocument();
  });

  it("says where the chunk is when the reader pages away, and offers a way back", async () => {
    pdf(13);
    finished(1, () => ({ positions: [{ page: 2, x0: 1, x1: 50, top: 1, bottom: 50 }] }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(1));
    await user.click(within(cardOf(1)).getByTestId("chunk-select"));
    await waitFor(() => expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 2 of 13"));
    await user.click(screen.getByTestId("preview-next"));
    expect(await screen.findByTestId("preview-away-note")).toHaveTextContent("The selected chunk is on page 2.");
    await user.click(screen.getByTestId("preview-goto"));
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 2 of 13");
  });

  it("keeps the selected chunk's boxes when the list is paged", async () => {
    pdf(13);
    finished(25);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(20));
    await user.click(within(cardOf(1)).getByTestId("chunk-select"));
    await screen.findByTestId("preview-box");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(cards()).toHaveLength(5));
    expect(screen.getByTestId("preview-box")).toBeInTheDocument();
  });
});

describe("URL state and FE-02", () => {
  it("clamps and cleans the parameters: a long search is cut, a bad show is 'all', a bad page is 1", async () => {
    finished(2);
    renderPage(`${chunkPath(DATASET_ID, DOC)}&page=abc&show=weird&keywords=${"k".repeat(150)}`);
    await waitUntil(() => listCalls().length > 0, { describe: "a chunk request" });
    const params = listCalls()[0]?.params as Record<string, string | number>;
    expect(params.page).toBe(1);
    expect(String(params.keywords).length).toBeLessThanOrEqual(100);
    expect(params.available).toBeUndefined();
  });

  it("writes page, search and filter to the address and leaves a default out", async () => {
    finished(25, (n) => ({ text: `needle ${n}` }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(20));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(location()).toContain("page=2"));
    await user.click(within(screen.getByTestId("chunk-filter")).getByText("On"));
    await waitFor(() => expect(location()).toContain("show=on"));
    expect(location()).not.toContain("page=");
    await user.type(screen.getByRole("searchbox", { name: "Search in chunks" }), "needle");
    await waitFor(() => expect(location()).toContain("keywords=needle"));
    await user.click(within(screen.getByTestId("chunk-filter")).getByText("All"));
    await waitFor(() => expect(location()).not.toContain("show="));
  });

  it("steps back to the last page when the address names a page past the end", async () => {
    finished(25);
    renderPage(`${chunkPath(DATASET_ID, DOC)}&page=9`);
    await waitFor(() => expect(location()).toContain("page=2"));
    await waitFor(() => expect(cards()).toHaveLength(5));
  });

  it("binds the workspace before any request: one chunk request, for the dataset's workspace, with page and search intact", async () => {
    const joined = [membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")];
    server.memberships = joined;
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t9", created_by: "u1" });
    useWorkspaceStore.getState().reset();
    useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(joined));
    finished(25, (n) => ({ text: `x marks the spot ${n}` }));
    const seen: Array<string | null> = [];
    const base = server.adapter;
    http.defaults.adapter = (config) => {
      if ((config.url ?? "").endsWith("/chunks")) seen.push(useWorkspaceStore.getState().activeTenantId);
      return base(config);
    };
    renderPage(`${chunkPath(DATASET_ID, DOC)}&page=2&keywords=x`);
    await waitFor(() => expect(cards()).toHaveLength(5));
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    expect(seen).toEqual(["t9"]);
    expect(listCalls()).toHaveLength(1);
    expect(listCalls()[0]?.params).toMatchObject({ page: 2, keywords: "x" });
    expect(location()).toContain("page=2");
    expect(location()).toContain("keywords=x");
    expect(screen.queryByTestId("gallery-page")).toBeNull();
  });

  it("leaves for the datasets page when the reader switches workspace afterwards", async () => {
    const joined = [membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")];
    server.memberships = joined;
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t9", created_by: "u1" });
    useWorkspaceStore.getState().reset();
    useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(joined));
    finished(1);
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(1));
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    act(() => useWorkspaceStore.getState().setActive("t1"));
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/datasets");
  });
});

describe("Permissions (D-10)", () => {
  it("tells a member who may not change the document that the chunks are read-only and draws no switch", async () => {
    finished(2);
    actAs(MEMBER, "normal", "u1");
    renderPage();
    expect(await screen.findByTestId("chunk-readonly-notice")).toBeInTheDocument();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.queryByTestId("chunk-switch")).toBeNull();
    expect(screen.queryByTestId("chunk-edit")).toBeNull();
    expect(screen.queryByTestId("chunk-add")).toBeNull();
  });

  it("draws the switch and no read-only notice for the person who may change it", async () => {
    finished(2);
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.getAllByTestId("chunk-switch")).toHaveLength(2);
    expect(screen.queryByTestId("chunk-readonly-notice")).toBeNull();
  });

  it("switches a chunk off from the page and keeps it in place", async () => {
    finished(3);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(3));
    await user.click(within(cardOf(2)).getByTestId("chunk-switch"));
    await waitFor(() => expect(cardOf(2)).toHaveAttribute("data-enabled", "false"));
    expect(cards()).toHaveLength(3);
  });
});

describe("Notices and states of the whole page", () => {
  it("shows the document-off notice while the chunks keep their own setting", async () => {
    finished(2);
    setFileExtra(server, DOC, { enabled: false });
    renderPage();
    expect(await screen.findByTestId("chunk-document-off-notice")).toBeInTheDocument();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(within(cardOf(1)).getByTestId("chunk-switch")).toBeChecked();
  });

  it("shows the parsing notice and no switch while the document is parsing and chunks are arriving", async () => {
    finished(2);
    advanceParse(server, DOC, { run: "1", progress: 0.4, chunkCount: 2 });
    renderPage();
    expect(await screen.findByTestId("chunk-parsing-notice")).toBeInTheDocument();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.queryByTestId("chunk-switch")).toBeNull();
  });

  it("shows the partly-indexed notice and opens the parsing details from it", async () => {
    finished(2);
    addFileLog(server, { id: "log".padEnd(32, "1"), docId: DOC, result: "failed" });
    advanceParse(server, DOC, { run: "4", error: { step: "embed", code: "provider_timeout", message: "x" } });
    const user = userEvent.setup();
    renderPage();
    const notice = await screen.findByTestId("chunk-partial-notice");
    await waitFor(() => expect(cards()).toHaveLength(2));
    await user.click(within(notice).getByRole("button", { name: "Details" }));
    expect(await screen.findByTestId("parsing-details")).toBeInTheDocument();
  });

  it("offers 'Parse document' for a document that was never parsed and sends the request", async () => {
    server.documents[DATASET_ID] = [firstDoc(), documentRow(2)];
    setChunks(server, DOC, []);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByTestId("chunk-empty-parse"));
    await waitUntil(() => server.callsTo("POST", `/api/v1/datasets/${DATASET_ID}/documents/parse`).length === 1, { describe: "parse request" });
    expect(JSON.parse(String(server.callsTo("POST", `/api/v1/datasets/${DATASET_ID}/documents/parse`)[0]?.data))).toMatchObject({ doc_ids: [DOC], run: "1" });
  });

  it("offers nothing to parse to a read-only caller", async () => {
    server.documents[DATASET_ID] = [firstDoc(), documentRow(2)];
    setChunks(server, DOC, []);
    actAs(MEMBER, "normal", "u1");
    renderPage();
    expect(await screen.findByText(/hasn't been parsed yet/)).toBeInTheDocument();
    expect(screen.queryByTestId("chunk-empty-parse")).toBeNull();
  });

  it("shows the parsing state for a document that is parsing with no chunks yet, with a cancel", async () => {
    server.documents[DATASET_ID] = [firstDoc({ run: "1", progress: 0.3 }), documentRow(2)];
    setChunks(server, DOC, []);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Parsing in progress" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel parsing" })).toBeInTheDocument();
  });

  it("shows the failed state with its reason and a way to parse again", async () => {
    server.documents[DATASET_ID] = [firstDoc({ run: "4" }), documentRow(2)];
    setFileExtra(server, DOC, { error: { step: "parse", code: "no_readable_text", message: "x" } });
    setChunks(server, DOC, []);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Parsing failed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse again" })).toBeInTheDocument();
  });

  it("refetches the list when the polled chunk count changes and once when parsing ends", async () => {
    server.documents[DATASET_ID] = [firstDoc({ run: "1", progress: 0.2 }), documentRow(2)];
    setChunks(server, DOC, []);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Parsing in progress" })).toBeInTheDocument();
    const first = listCalls().length;
    setChunks(server, DOC, [chunkRow(1), chunkRow(2)]);
    advanceParse(server, DOC, { run: "1", progress: 0.5, chunkCount: 2 });
    await waitFor(() => expect(cards()).toHaveLength(2), { timeout: 8000 });
    expect(listCalls().length).toBe(first + 1);
    setChunks(server, DOC, [chunkRow(1), chunkRow(2), chunkRow(3)]);
    advanceParse(server, DOC, { run: "3", chunkCount: 3 });
    await waitFor(() => expect(cards()).toHaveLength(3), { timeout: 8000 });
    expect(listCalls().length).toBe(first + 2);
  });
});
