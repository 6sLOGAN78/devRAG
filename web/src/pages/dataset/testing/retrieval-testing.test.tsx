import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, registerQueryClient } from "@/services/http";
import { toSourceHit } from "@/services/chat-service";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DATASET_ID, createDatasetServer, datasetRow, documentRow, membershipRow, storedMemberships } from "@/test/dataset-server";
import { OWNER } from "@/test/files-harness";
import { setHits } from "@/test/server-areas/retrieval";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";
import RetrievalTestingPage from ".";
import { HitCard } from "./hit-card";
import { RetrievalControls, type RetrievalValues } from "./retrieval-controls";

const defaults = (): RetrievalValues => ({ question: "", threshold: 0.2, weight: 0.3, rerankId: "" });
describe("retrieval controls and hit card", () => {
  function controls() {
    const onRun = vi.fn(); function Host() { const [values, setValues] = useState(defaults()); return <RetrievalControls values={values} onChange={setValues} onReset={() => setValues({ ...defaults(), question: values.question })} onRun={onRun} running={false} models={[]} />; }
    render(<Host />); return onRun;
  }
  it("starts at the calibrated threshold and vector defaults", () => { controls(); expect(screen.getByTestId("field-retrieval-threshold")).toHaveValue("0.2"); expect(screen.getByTestId("field-retrieval-weight")).toHaveValue("0.3"); });
  it("does not run on a slider change", () => { const run = controls(); fireEvent.change(screen.getByTestId("field-retrieval-threshold"), { target: { value: "0.6" } }); expect(run).not.toHaveBeenCalled(); });
  it("resets the settings while preserving the question", () => { controls(); fireEvent.change(screen.getByTestId("field-retrieval-question"), { target: { value: "Question" } }); fireEvent.change(screen.getByTestId("field-retrieval-weight"), { target: { value: "0.9" } }); fireEvent.click(screen.getByTestId("retrieval-reset")); expect(screen.getByTestId("field-retrieval-weight")).toHaveValue("0.3"); expect(screen.getByTestId("field-retrieval-question")).toHaveValue("Question"); });
  it.each(["ctrlKey", "metaKey"])("runs with Enter and %s", (key) => { const run = controls(); const input = screen.getByTestId("field-retrieval-question"); fireEvent.change(input, { target: { value: "Question" } }); fireEvent.keyDown(input, { key: "Enter", [key]: true }); expect(run).toHaveBeenCalledOnce(); });
  it("validates the 2000-character question cap", () => { const run = controls(); fireEvent.change(screen.getByTestId("field-retrieval-question"), { target: { value: "x".repeat(2001) } }); fireEvent.click(screen.getByTestId("retrieval-run")); expect(screen.getByText("Use 2,000 characters or fewer.")).toBeInTheDocument(); expect(run).not.toHaveBeenCalled(); });
  const card = (over = {}, reranked = false) => render(<HitCard hit={toSourceHit({ chunk_id: "c1", doc_name: "report.txt", content: "Short passage", similarity: 0.75, term_similarity: null, vector_similarity: 0.5, rerank_similarity: 0.8, ...over })} rank={1} reranked={reranked} onSource={vi.fn()} />);
  it("renders a null score as an accessible dash", () => { card(); expect(screen.getByTestId("hit-score-term")).toHaveTextContent("—"); expect(screen.getByTestId("hit-score-term")).toHaveTextContent("Not available"); });
  it("sets the overall bar from similarity", () => { card(); expect(screen.getByTestId("hit-overall-bar")).toHaveAttribute("aria-valuenow", "75"); expect(screen.getByTestId("hit-overall-bar").firstElementChild).toHaveStyle({ width: "75%" }); });
  it("only adds a passage toggle for long content", () => { const view = card(); expect(screen.queryByTestId("hit-toggle")).toBeNull(); view.unmount(); card({ content: "Long passage. ".repeat(100) }); fireEvent.click(screen.getByTestId("hit-toggle")); expect(screen.getByTestId("hit-toggle")).toHaveAttribute("aria-expanded", "true"); });
  it("shows a rerank score only for reranked results", () => { const view = card(); expect(screen.queryByTestId("hit-score-rerank")).toBeNull(); view.unmount(); card({}, true); expect(screen.getByTestId("hit-score-rerank")).toHaveTextContent("0.80"); });
});

describe("retrieval testing page", () => {
  const server = createDatasetServer(), adapter = http.defaults.adapter; let client: QueryClient;
  const hit = (id: string, content: string, vector: number) => ({ chunk_id: id, dataset_id: DATASET_ID, doc_id: "d".repeat(32), doc_name: `${id}.txt`, content, vector_similarity: vector, rerank_similarity: 0.8 });
  beforeEach(() => {
    server.reset(); http.defaults.adapter = server.adapter; server.datasets[DATASET_ID] = datasetRow(); server.documents[DATASET_ID] = [documentRow(1, { chunk_num: 3 })];
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); registerQueryClient(client); setAuthorization("test-token"); useUserStore.getState().setUser(OWNER); useWorkspaceStore.getState().reset(); useWorkspaceStore.getState().initialise("u1", "t1", []);
    setHits(server, [hit("a", "alpha beta", 0.1), hit("b", "alpha", 0.9), hit("c", "other", 0.95)]);
    server.use(({ method, url, ok }) => {
      if (method === "GET" && url === "/api/v1/models") return ok([{ id: "rank@TEI", name: "rank", provider: "TEI", type: "rerank" }]);
      return undefined;
    });
  });
  afterEach(() => { cleanup(); client.clear(); http.defaults.adapter = adapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); vi.restoreAllMocks(); });
  function mount(id = DATASET_ID) { const router = createMemoryRouter([{ path: "/dataset/testing", element: <RetrievalTestingPage /> }], { initialEntries: [`/dataset/testing?id=${id}`] }); return { ...render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>), router }; }
  const ready = () => waitUntil(() => screen.queryByTestId("field-retrieval-question"));
  const question = () => fireEvent.change(screen.getByTestId("field-retrieval-question"), { target: { value: "alpha beta" } });
  const run = async () => { fireEvent.click(screen.getByTestId("retrieval-run")); await waitUntil(() => screen.queryByTestId("retrieval-results") && screen.getByTestId("retrieval-run").getAttribute("aria-busy") !== "true"); };
  it("is idle before the first requested run", async () => { mount(); await ready(); expect(screen.getByTestId("retrieval-idle")).toBeInTheDocument(); expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(0); });
  it("makes no search request on control changes and one on Run", async () => { mount(); await ready(); question(); fireEvent.change(screen.getByTestId("field-retrieval-threshold"), { target: { value: "0.25" } }); expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(0); await run(); expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(1); });
  it("drops hits after raising threshold and explicitly running again", async () => { mount(); await ready(); question(); await run(); expect(screen.getAllByTestId("hit-card")).toHaveLength(3); fireEvent.change(screen.getByTestId("field-retrieval-threshold"), { target: { value: "0.7" } }); await run(); expect(screen.getAllByTestId("hit-card")).toHaveLength(1); });
  it("changes ranking after a weight change and a new run", async () => { mount(); await ready(); question(); await run(); expect(screen.getAllByTestId("hit-card")[0]).toHaveAttribute("data-chunk-id", "a"); fireEvent.change(screen.getByTestId("field-retrieval-weight"), { target: { value: "0.95" } }); await run(); expect(screen.getAllByTestId("hit-card")[0]).toHaveAttribute("data-chunk-id", "c"); });
  it("marks existing results stale after controls change", async () => { mount(); await ready(); question(); expect(screen.queryByTestId("retrieval-stale")).toBeNull(); await run(); fireEvent.change(screen.getByTestId("field-retrieval-weight"), { target: { value: "0.6" } }); expect(screen.getByTestId("retrieval-stale")).toBeInTheDocument(); expect(screen.getAllByTestId("hit-card")).toHaveLength(3); });
  it("shows rerank status, score and timing only after a reranked run", async () => { mount(); await ready(); question(); fireEvent.change(screen.getByTestId("field-retrieval-rerank"), { target: { value: "rank@TEI" } }); await run(); expect(screen.getByTestId("retrieval-reranked")).toHaveTextContent("Reranked"); expect(screen.getByTestId("retrieval-timings")).toHaveTextContent("Rerank"); expect(screen.getAllByTestId("hit-score-rerank")).not.toHaveLength(0); });
  it("keeps previous results and pagination focus while fetching a page", async () => {
    setHits(server, Array.from({ length: 21 }, (_, n) => hit(String(n), "alpha beta", 0.5))); mount(); await ready(); question(); await run(); const next = within(screen.getByRole("navigation", { name: "Result pages" })).getByRole("button", { name: "Next" }); next.focus();
    let release = () => {}; server.holds["POST /api/v1/datasets/search"] = new Promise<void>((resolve) => { release = resolve; }); await userEvent.keyboard("{Enter}");
    await waitUntil(() => server.callsTo("POST", "/api/v1/datasets/search").length === 2); expect(next).toHaveFocus(); expect(screen.getAllByTestId("hit-card")).toHaveLength(10); await act(async () => release()); await waitUntil(() => screen.getAllByTestId("hit-card")[0]?.dataset.rank === "11"); expect(next).toHaveFocus();
  });
  it("shows a running state without unmounting the question field", async () => {
    let release = () => {}; server.holds["POST /api/v1/datasets/search"] = new Promise<void>((resolve) => { release = resolve; }); mount(); await ready(); question(); const input = screen.getByTestId("field-retrieval-question"); fireEvent.click(screen.getByTestId("retrieval-run")); await waitUntil(() => screen.queryByTestId("retrieval-running")); expect(screen.getByTestId("field-retrieval-question")).toBe(input); await act(async () => release());
  });
  it("offers reset when no passages match", async () => { setHits(server, []); mount(); await ready(); question(); await run(); expect(screen.getByTestId("retrieval-empty")).toHaveTextContent("No passages matched"); });
  it("explains an unparsed dataset after a zero-hit run", async () => { server.documents[DATASET_ID] = []; setHits(server, []); mount(); await ready(); question(); await run(); expect(screen.getByTestId("retrieval-no-chunks")).toBeInTheDocument(); expect(screen.getByRole("link", { name: "Open documents" })).toHaveAttribute("href", `/dataset/files?id=${DATASET_ID}`); });
  it("keeps the question while reporting a fixed search refusal", async () => { server.forced["POST /api/v1/datasets/search"] = { status: 502, reason: "rerank_unavailable", message: "Hostile server text" }; mount(); await ready(); question(); fireEvent.click(screen.getByTestId("retrieval-run")); await waitUntil(() => screen.queryByTestId("retrieval-error")); expect(screen.getByTestId("field-retrieval-question")).toHaveValue("alpha beta"); expect(screen.getByTestId("retrieval-error")).not.toHaveTextContent("Hostile server text"); });
  it("does not request a malformed dataset id", () => { mount("bad"); expect(screen.getByTestId("retrieval-not-found")).toBeInTheDocument(); expect(server.calls).toHaveLength(0); });
  it("uses the not-found block for an inaccessible dataset and never searches", async () => { server.forced[`GET /api/v1/datasets/${DATASET_ID}`] = { status: 404, message: "gone" }; mount(); await waitUntil(() => screen.queryByTestId("retrieval-not-found")); expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(0); });
  it("waits for workspace binding before loading models or enabling search", async () => { useWorkspaceStore.getState().reset(); mount(); await waitUntil(() => server.callsTo("GET", `/api/v1/datasets/${DATASET_ID}`).length > 0); expect(server.callsTo("GET", "/api/v1/models")).toHaveLength(0); expect(screen.queryByTestId("retrieval-run")).toBeNull(); act(() => useWorkspaceStore.getState().initialise("u1", "t1", [])); await ready(); });
  it("keeps questions out of the URL and does not replay them on reload", async () => { const view = mount(); await ready(); question(); await run(); expect(view.router.state.location.search).toBe(`?id=${DATASET_ID}`); view.unmount(); mount(); await ready(); expect(screen.getByTestId("field-retrieval-question")).toHaveValue(""); expect(screen.getByTestId("retrieval-idle")).toBeInTheDocument(); });
  it("opens a hit in the shared drawer and restores its View source button", async () => { mount(); await ready(); question(); await run(); fireEvent.click(screen.getAllByTestId("hit-source")[0]!); await waitUntil(() => screen.queryByTestId("source-passage")); expect(screen.getByTestId("source-title")).toHaveTextContent("Result 1"); fireEvent.click(screen.getByTestId("source-close")); await waitUntil(() => document.activeElement === screen.getAllByTestId("hit-source")[0]); });
  it("sends the joined workspace after binding a deep-linked dataset", async () => {
    server.datasets[DATASET_ID]!.tenant_id = "t2"; server.memberships = [membershipRow("t2", "Joined workspace", "normal")]; useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(server.memberships));
    mount(); await ready(); question(); await run(); expect(useWorkspaceStore.getState().activeTenantId).toBe("t2");
    const sent = JSON.parse(String(server.callsTo("POST", "/api/v1/datasets/search")[0]?.data)); expect(sent.tenant_id).toBe("t2");
  });
  it("performs a fresh request when the same settings are explicitly run twice", async () => { mount(); await ready(); question(); await run(); await run(); expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(2); });
});
