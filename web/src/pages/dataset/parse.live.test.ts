import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, configure, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { buildRoutes } from "@/routes";
import { createDataset, deleteDatasets } from "@/services/dataset-service";
import { uploadDocument } from "@/services/document-service";
import { http, registerNavigate, registerQueryClient } from "@/services/http";
import { listModels, saveDefaults, saveProvider } from "@/services/model-service";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { FAKE_EMBEDDING_DIMENSION, startFakeProvider, type FakeProvider } from "@/test/live/fake-provider";
import { textFile } from "@/test/live/documents";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

// The first Phase 4 screen against the real stack (UI-15, DOC-09, DOC-10, E2E-05): the real dataset page, the real HTTP
// client, the real API, the real queue and the real executor container. Only the third-party embedding provider is the
// loopback fake of Phase 3; the real provider key never enters the browser tier (T-03-22-04).
const PASSWORD = ["live", "parse", "pass", "0001"].join("-");
const FAKE_PROVIDER_CREDENTIAL = ["fake", "parse", "journey", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const PROVIDER_SLUG = "openai-compatible";
const EMBED_MODEL = "fake-embed";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

let fake: FakeProvider;
let session = "";
let tenantId = "";
let userId = "";
let datasetId = "";
let router: ReturnType<typeof createMemoryRouter> | null = null;

async function call<T>(path: string, init: { method?: string; bearer?: string; body?: unknown } = {}): Promise<{ status: number; envelope: Envelope<T> | null }> {
  const response = await fetch(new URL(path, window.location.origin), {
    method: init.method ?? "GET",
    headers: { "Content-Type": "application/json", ...(init.bearer ? { Authorization: `Bearer ${init.bearer}` } : {}) },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  let envelope: Envelope<T> | null = null;
  try {
    envelope = (await response.json()) as Envelope<T>;
  } catch {
    envelope = null;
  }
  return { status: response.status, envelope };
}

beforeAll(async () => {
  configure({ getElementError: (message) => new Error(message ?? "element not found") });
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
  await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  fake = await startFakeProvider();

  const email = `webparse-${suffix}@example.test`;
  const registered = await call("/api/v1/users", { method: "POST", body: { email, password: PASSWORD, nickname: `webparse-${suffix}` } });
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
  if (registered.status !== 200 || registered.envelope?.code !== 0) throw new Error(`registering returned HTTP ${registered.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: PASSWORD } });
  session = (login.envelope?.code === 0 && login.envelope.data?.token) || "";
  if (!session) throw new Error(`signing in returned HTTP ${login.status}`);
  const info = await call<{ id: string; tenant_id: string }>("/v1/user/info", { bearer: session });
  tenantId = info.envelope?.data?.tenant_id ?? "";
  userId = info.envelope?.data?.id ?? "";
  if (!tenantId || !userId) throw new Error(`reading the account returned HTTP ${info.status}`);

  setAuthorization(session);
  await saveProvider({ tenantId, provider: PROVIDER_SLUG, apiKey: FAKE_PROVIDER_CREDENTIAL, baseUrl: fake.stackBaseUrl, models: [{ name: EMBED_MODEL, type: "embedding" }] });
  const models = await listModels(tenantId, "embedding");
  const embedding = models.find((model) => model.name === EMBED_MODEL);
  expect(embedding?.dimension).toBe(FAKE_EMBEDDING_DIMENSION);
  await saveDefaults(tenantId, { embedding: embedding?.id ?? "" });
  const dataset = await createDataset({ tenantId, name: `Parse journey ${suffix}`, permission: "me", embdId: embedding?.id });
  datasetId = dataset.id;
  removeAuthorization();
});

afterEach(() => {
  cleanup();
  registerNavigate(null);
  removeAuthorization();
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

afterAll(async () => {
  // Cleanup by recorded id and tenant: deleting the dataset removes its rows, index documents and blobs; the account is
  // removed by the runner from LIVE_ACCOUNTS_FILE.
  if (datasetId) {
    setAuthorization(session);
    await deleteDatasets([datasetId], tenantId).catch(() => []);
    removeAuthorization();
  }
  await fake?.close();
});

describe("live parse journey on the dataset page (UI-15, DOC-09, DOC-10, E2E-05)", () => {
  it("takes an uploaded TXT from Not started through Parsing to Finished with its chunk count and no reload", async () => {
    const user = userEvent.setup();
    setAuthorization(session);
    const uploaded = await uploadDocument(datasetId, textFile(3, "notes.txt"));
    expect(uploaded.run).toBe("0");

    cleanup();
    removeAuthorization();
    useUserStore.getState().reset();
    useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null, bound: null });
    window.localStorage.removeItem("devrag.workspace");
    setAuthorization(session);
    router = createMemoryRouter(buildRoutes(), { initialEntries: [`/dataset/files?id=${datasetId}`] });
    const client = new QueryClient();
    registerQueryClient(client);
    const current = router;
    registerNavigate({
      navigate: (to) => current.navigate(to, { replace: true }),
      currentPath: () => `${current.state.location.pathname}${current.state.location.search}`,
    });

    // Every document-list request the client sends, recorded with the application's own axios instance.
    const listCalls: number[] = [];
    let pressed = false;
    const interceptor = http.interceptors.request.use((config) => {
      if (pressed && /\/documents$/.test(config.url ?? "") && (config.method ?? "get").toLowerCase() === "get") listCalls.push(Date.now());
      return config;
    });

    render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router: current }), createElement(Toaster)));
    await waitUntil(() => client.getQueryState(MEMBERSHIPS_QUERY_KEY)?.status === "success", { describe: "the membership list to load", timeout: 30_000 });
    await waitUntil(() => useWorkspaceStore.getState().initialisedFor === userId, { describe: "the workspace store to initialise", timeout: 30_000 });

    const page = await screen.findByTestId("dataset-page", {}, { timeout: 30_000 });
    const row = await waitUntil(() => screen.queryAllByTestId("document-row")[0] ?? null, { describe: "the document row", timeout: 30_000 });
    expect(row).toHaveTextContent("notes.txt");
    expect(row.getAttribute("data-run")).toBe("0");
    expect(within(row).getByTestId("document-status")).toHaveTextContent("Not started");
    expect(within(row).getByTestId("document-progress")).toHaveTextContent("0%");

    // The same DOM node must survive to the end: no reload, no remount of the page.
    page.setAttribute("data-journey-marker", suffix);

    pressed = true;
    await user.click(within(row).getByRole("button", { name: "Parse notes.txt" }));

    // While it runs, the bar never reads 100.
    const seen: number[] = [];
    await waitUntil(
      () => {
        for (const bar of screen.queryAllByTestId("document-progress-bar")) {
          const now = bar.getAttribute("aria-valuenow") ?? bar.querySelector("[aria-valuenow]")?.getAttribute("aria-valuenow");
          if (now !== null && now !== undefined) seen.push(Number(now));
        }
        return screen.queryAllByTestId("document-row")[0]?.getAttribute("data-run") === "3";
      },
      { describe: "the row to reach Finished (data-run 3)", timeout: 120_000, interval: 50 },
    );
    expect(seen.every((value) => value <= 99)).toBe(true);

    const done = screen.getAllByTestId("document-row")[0];
    await waitUntil(() => within(done).getByTestId("document-status").textContent === "Finished" || /Finished/.test(within(done).getByTestId("document-status").textContent ?? ""), { describe: "the badge to read Finished" });
    expect(within(done).getByTestId("document-status")).toHaveTextContent("Finished");
    expect(within(done).getByTestId("document-status-detail")).toHaveTextContent("3 chunks");
    expect(within(done).getByTestId("document-progress")).toHaveTextContent("100%");
    await waitUntil(() => screen.queryByTestId("summary-count-done")?.textContent === "1" && screen.queryByTestId("summary-count-chunk-total")?.textContent === "3", {
      describe: "the summary card to read Finished 1 and Chunks 3",
      timeout: 30_000,
    });
    await waitUntil(() => within(screen.getByTestId("dataset-meta")).queryByText("3 chunks") !== null, { describe: "the meta line to read 3 chunks", timeout: 30_000 });

    // No reload: same header node, still marked, and the list was refreshed by polling after the press.
    expect(screen.getByTestId("dataset-page")).toBe(page);
    expect(page.getAttribute("data-journey-marker")).toBe(suffix);
    expect(listCalls.length).toBeGreaterThanOrEqual(2);
    http.interceptors.request.eject(interceptor);

    // Success is quiet.
    expect(document.querySelectorAll("[data-sonner-toast]")).toHaveLength(0);
    // The real executor called the loopback provider for the three chunks.
    expect(fake.paths.filter((path) => path === "/v1/embeddings").length).toBeGreaterThan(0);
  }, 240_000);
});
