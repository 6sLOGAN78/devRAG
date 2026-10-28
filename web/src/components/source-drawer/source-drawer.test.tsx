import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerQueryClient } from "@/services/http";
import { toReference, toSourceHit } from "@/services/chat-service";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { setFileExtra } from "@/test/server-areas/files";
import { waitUntil } from "@/test/wait-until";
import { SourceDrawer } from ".";
import { useUserStore } from "@/stores/user-store";
import { sourceFromHit, sourceFromReference, type SourceView } from "./source-model";

useFilesServer();
const DOC = documentRow(1).id, DOC_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}`, IMAGE = `${DOC_URL}/pages/3/image`;
const position = (page = 3) => ({ page, x0: 10, x1: 100, top: 20, bottom: 60 });
const raw = (over = {}) => ({ index: 3, chunk_id: "chunk-one", doc_id: DOC, dataset_id: DATASET_ID, doc_name: "report.pdf", content: "A saved passage.", positions: [position()], page_sizes: { "3": [595, 842] }, similarity: 0.8, term_similarity: 0.6, vector_similarity: 0.9, rerank_similarity: null, ...over });
const source = (over = {}) => sourceFromReference(toReference({ chunks: [raw(over)] }), 3)!;
describe("source drawer", () => {
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); registerQueryClient(client);
    setFileExtra(server, DOC, { preview: "pages", pagesTotal: 6 });
    vi.stubGlobal("URL", Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => "blob:source-test"), revokeObjectURL: vi.fn() }));
  });
  afterEach(() => { client.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  const show = (value = source(), open = true) => render(<MemoryRouter><QueryClientProvider client={client}><SourceDrawer source={value} open={open} onOpenChange={vi.fn()} /></QueryClientProvider></MemoryRouter>);
  it("finds a sparse reference by index and uses a one-based label", () => { expect(source()).toMatchObject({ kind: "chat", number: 4, content: "A saved passage." }); expect(sourceFromReference(toReference({ chunks: [raw()] }), 0)).toBeNull(); });
  it("does not normalize an unavailable reference into an openable source", () => expect(sourceFromReference(toReference({ chunks: [{ index: 3, unavailable: true }] }), 3)).toBeNull());
  it("normalizes a retrieval hit with the supplied rank", () => expect(sourceFromHit(toSourceHit(raw()), 7)).toMatchObject({ kind: "hit", number: 7, docName: "report.pdf" }));
  it("formats present scores to two decimals and omits null", () => { show(); expect(screen.getByTestId("source-score-overall")).toHaveTextContent("0.80"); expect(screen.getByTestId("source-score-term")).toHaveTextContent("0.60"); expect(screen.queryByTestId("source-score-rerank")).toBeNull(); });
  it("omits non-finite scores", () => { show(source({ similarity: NaN, term_similarity: Infinity, vector_similarity: null })); expect(screen.queryByTestId("source-score-overall")).toBeNull(); expect(screen.queryByText("NaN")).toBeNull(); });
  it("focuses the passage on open", () => { show(); expect(screen.getByRole("region", { name: "Passage text" })).toHaveFocus(); });
  it("shows the first cited PDF page with this chunk's boxes", async () => { show(); await waitUntil(() => screen.queryByTestId("preview-image")); expect(screen.getByTestId("preview-caption")).toHaveTextContent("3"); expect(screen.getByTestId("preview-box")).toHaveStyle({ pointerEvents: "none" }); expect(screen.getByTestId("source-open-document")).toHaveAttribute("href", `/document?id=${DATASET_ID}&doc=${DOC}&page=3`); });
  it("requests the page with an Authorization header and no token in its URL", async () => {
    show(); await waitUntil(() => server.callsTo("GET", IMAGE).length > 0); const call = server.callsTo("GET", IMAGE)[0]!;
    expect(call.headers.get("Authorization")).toBe("Bearer tok-session"); expect(call.url).not.toContain("tok-session"); expect(call.url).not.toContain("token=");
  });
  it("lists distinct pages and previews another page of a multi-page chunk", async () => {
    show(source({ positions: [position(3), position(4), position(3)] })); expect(screen.getByTestId("source-pages")).toHaveTextContent("3, 4");
    await waitUntil(() => screen.queryByTestId("preview-next")); fireEvent.click(screen.getByTestId("preview-next")); await waitUntil(() => server.callsTo("GET", `${DOC_URL}/pages/4/image`).length > 0);
  });
  it("shows no preview or placeholder for a positionless PDF", async () => { show(source({ positions: [] })); await waitUntil(() => server.callsTo("GET", DOC_URL).length > 0); expect(screen.queryByTestId("source-preview")).toBeNull(); expect(screen.getByTestId("source-passage")).toHaveTextContent("A saved passage."); });
  it("shows text only for a non-PDF", async () => { setFileExtra(server, DOC, { preview: "none", pagesTotal: null }); show(source({ doc_name: "notes.txt", positions: [] })); expect(screen.queryByTestId("source-preview")).toBeNull(); });
  it("keeps the saved text and removes Open document after a detail 404", async () => {
    server.forced[`GET ${DOC_URL}`] = { status: 404, message: "gone" }; show(); await waitUntil(() => screen.queryByTestId("source-gone")); expect(screen.getByTestId("source-passage")).toHaveTextContent("A saved passage."); expect(screen.queryByTestId("source-open-document")).toBeNull();
  });
  it("leaves the passage untouched when a page image fails and allows retry", async () => {
    server.forced[`GET ${IMAGE}`] = { status: 502, message: "failure" }; show(); await waitUntil(() => screen.queryByTestId("preview-error")); expect(screen.getByTestId("source-passage")).toHaveTextContent("A saved passage.");
    delete server.forced[`GET ${IMAGE}`]; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await waitUntil(() => screen.queryByTestId("preview-image"));
  });
  it("renders hostile passage and document names as text", () => { const view = show(source({ content: "<script>alert(1)</script>", doc_name: "<img src=x onerror=alert(1)>" })); expect(screen.getByTestId("source-passage")).toHaveTextContent("<script>alert(1)</script>"); expect(view.container.querySelector("script")).toBeNull(); expect(screen.getByTestId("source-document")).toHaveTextContent("<img src=x onerror=alert(1)>"); });
  it("does not mount the body or request anything while closed", () => { show(source(), false); expect(screen.queryByTestId("source-drawer")).toBeNull(); expect(server.callsTo("GET", DOC_URL)).toHaveLength(0); });
  it("uses the hit title for a retrieval source", () => { show(sourceFromHit(toSourceHit(raw()), 2)); expect(screen.getByTestId("source-title")).toHaveTextContent("Result 2"); });
  it("restores the opener and mounts fresh content for a different source", async () => {
    function Host() {
      const [value, setValue] = useState<SourceView | null>(null);
      return <><button onClick={() => setValue(source())}>Open first</button><button onClick={() => setValue(source({ content: "Second passage", positions: [] }))}>Open second</button><SourceDrawer source={value} open={value !== null} onOpenChange={() => setValue(null)} onCloseAutoFocus={(event) => { event.preventDefault(); screen.queryByRole("button", { name: "Open first" })?.focus(); }} /></>;
    }
    render(<MemoryRouter><QueryClientProvider client={client}><Host /></QueryClientProvider></MemoryRouter>); fireEvent.click(screen.getByRole("button", { name: "Open first" })); await waitUntil(() => screen.queryByTestId("source-passage")); fireEvent.click(screen.getByTestId("source-close")); await waitUntil(() => document.activeElement === screen.getByRole("button", { name: "Open first" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Open second" }))); expect(screen.getByTestId("source-passage")).toHaveTextContent("Second passage"); expect(screen.queryByTestId("source-preview")).toBeNull();
  });
  it("renders extracted figures from an authenticated blob and keeps hostile captions as text", async () => {
    const id = "a".repeat(32), url = `/api/v1/documents/images/${id}`;
    setFileExtra(server, DOC, { assets: [{ id, kind: "image", caption: "<img src=x onerror=alert(1)>", page: 3, width: 1400, height: 400 }] });
    server.use(({ config, url: called }) => called === url ? { data: new Blob(["PNG bytes"], { type: "image/png" }), status: 200, statusText: "OK", headers: {}, config } : undefined);
    const view = show();
    await waitUntil(() => screen.queryByTestId("source-asset-image"));
    expect(screen.getByTestId("source-asset-image")).toHaveAttribute("src", "blob:source-test");
    expect(screen.getByTestId("source-asset-caption")).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(view.container.querySelector("img[onerror]")).toBeNull();
    const call = server.callsTo("GET", url)[0]!;
    expect(call.headers.get("Authorization")).toBe("Bearer tok-session"); expect(call.url).not.toContain("token=");
    view.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:source-test");
  });

  it("keeps passage text when a figure fails and retries the authenticated request", async () => {
    const id = "b".repeat(32), url = `/api/v1/documents/images/${id}`;
    setFileExtra(server, DOC, { preview: "none", assets: [{ id, kind: "image", caption: "Figure", page: null, width: 100, height: 40 }] });
    server.use(({ config, url: called }) => called === url ? { data: new Blob(["pixels"], { type: "image/png" }), status: 200, statusText: "OK", headers: {}, config } : undefined);
    server.forced[`GET ${url}`] = { status: 503, message: "temporarily unavailable" };
    show(source({ positions: [] }));
    await waitUntil(() => screen.queryByText("This figure is unavailable."));
    expect(screen.getByTestId("source-passage")).toHaveTextContent("A saved passage.");
    delete server.forced[`GET ${url}`]; fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitUntil(() => screen.queryByTestId("source-asset-image"));
    expect(server.callsTo("GET", url)).toHaveLength(2);
  });
  it("revokes an old figure when the workspace changes before new detail arrives", async () => {
    const id = "c".repeat(32), url = `/api/v1/documents/images/${id}`;
    setFileExtra(server, DOC, { preview: "none", assets: [{ id, kind: "image", caption: "Figure", page: null, width: 100, height: 40 }] });
    server.use(({ config, url: called }) => called === url ? { data: new Blob(["pixels"], { type: "image/png" }), status: 200, statusText: "OK", headers: {}, config } : undefined);
    show(source({ positions: [] })); await waitUntil(() => screen.queryByTestId("source-asset-image"));
    let release!: () => void;
    server.holds[`GET ${DOC_URL}`] = new Promise<void>((resolve) => { release = resolve; });
    await act(async () => useUserStore.getState().setUser({ ...useUserStore.getState().user!, tenantId: "t2", tenantName: "Another workspace" }));
    expect(screen.queryByTestId("source-asset-image")).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:source-test");
    expect(server.callsTo("GET", url)).toHaveLength(1);
    release();
  });

  it("shows merged structured cells and the matching authenticated crop without executing cell markup", async () => {
    const id = "d".repeat(32), url = `/api/v1/documents/images/${id}`;
    setFileExtra(server, DOC, { preview: "none", assets: [{ id, kind: "table", caption: "Orchard measurements", page: 1, width: 900, height: 600 }] });
    server.use(({ config, url: called }) => called === url ? { data: new Blob(["pixels"], { type: "image/png" }), status: 200, statusText: "OK", headers: {}, config } : undefined);
    const table = { rows: 2, columns: 2, caption: "Orchard measurements", asset_id: id, cells: [
      { row: 0, column: 0, text: "ORCHARD", rowspan: 1, colspan: 2, header: true },
      { row: 1, column: 0, text: "<img src=x onerror=alert(1)>", rowspan: 1, colspan: 1, header: false },
      { row: 1, column: 1, text: "", rowspan: 1, colspan: 1, header: false },
    ] };
    show(source({ positions: [], tables: [table] }));
    await waitUntil(() => screen.queryByTestId("source-structured-table"));
    expect(screen.getByRole("columnheader", { name: "ORCHARD" })).toHaveAttribute("colspan", "2");
    expect(screen.getByRole("cell", { name: "<img src=x onerror=alert(1)>" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "" })).toBeEmptyDOMElement();
    expect(document.querySelector('[data-testid="source-drawer"] img[onerror]')).toBeNull();
    await waitUntil(() => screen.queryByTestId("source-asset-image"));
    expect(server.callsTo("GET", url)).toHaveLength(1);
  });

  it("renders original Markdown source code and parameter tables without fetching diagrams", () => {
    show(source({ doc_name:"manual.md",positions:[],content:'# Setup\n\n````python\npayload = "```"\nprint(52)\n````\n\n| Parameter | Value |\n|---|---|\n| harvest | 9100 |\n\n![diagram 52](https://example.invalid/tracker.png)\n\n<script>window.manualExecuted=true</script>' }));
    const passage=screen.getByTestId("source-passage");
    expect(passage.querySelector("pre code")?.textContent).toBe('payload = "```"\nprint(52)\n');
    expect(passage.querySelector("table")).not.toBeNull();
    expect(passage.querySelector("img,script")).toBeNull();
    expect(passage.textContent).toContain("diagram 52");
  });
});
