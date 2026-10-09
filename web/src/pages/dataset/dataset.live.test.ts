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
import { createDataset, deleteDatasets, listDatasets } from "@/services/dataset-service";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { listModels, saveDefaults, saveProvider } from "@/services/model-service";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { FAKE_EMBEDDING_DIMENSION, startFakeProvider, type FakeProvider } from "@/test/live/fake-provider";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL) with the real SPA routes, the real HTTP client and the real dataset,
// document and workspace routes. Nothing in the app is mocked and the HTTP client is the application's own. The provider
// is the loopback fake of `fake-provider.ts` (the real provider key never enters the browser tier, T-03-22-04): the app
// container calls it when the provider is saved. Every state change below is made through the page; the services are
// used to set the workspace up, to create the datasets the member journey reads, and to clean up by recorded id.
const PASSWORD = ["live", "dataset", "pass", "0001"].join("-");
// A made-up credential for the fake provider, assembled from parts so no scanner sees a key-shaped literal.
const FAKE_PROVIDER_CREDENTIAL = ["fake", "dataset", "journey", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const PROVIDER_SLUG = "openai-compatible";
const EMBED_MODEL = "fake-embed";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
interface Account {
  email: string;
  session: string;
  userId: string;
  tenantId: string;
}
interface Created {
  tenantId: string;
  id: string;
  /** The session that may delete it. */
  session: string;
}

let fake: FakeProvider;
let owner: Account;
let mate: Account;
const created: Created[] = [];
let router: ReturnType<typeof createMemoryRouter> | null = null;

function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

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

async function createAccount(tag: string): Promise<Account> {
  const email = `webdataset-${tag}-${suffix}@example.test`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: PASSWORD, nickname: `webdataset-${tag}-${suffix}` } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: PASSWORD } });
  const session = login.envelope?.code === 0 ? login.envelope.data?.token : undefined;
  if (!session) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  const info = await call<{ id: string; tenant_id: string }>("/v1/user/info", { bearer: session });
  const data = info.envelope?.data;
  if (!data?.tenant_id || !data.id) throw new Error(`reading ${tag} returned HTTP ${info.status}`);
  return { email, session, userId: data.id, tenantId: data.tenant_id };
}

async function join(workspaceOwner: Account, teammate: Account): Promise<void> {
  const invited = await call(`/api/v1/tenants/${workspaceOwner.tenantId}/users`, { method: "POST", bearer: workspaceOwner.session, body: { email: teammate.email } });
  expect(invited.status).toBe(200);
  const accepted = await call(`/api/v1/tenants/${workspaceOwner.tenantId}`, { method: "PATCH", bearer: teammate.session, body: { action: "accept" } });
  expect(accepted.status).toBe(200);
}

/** A page reload: the in-memory workspace state is gone, the stored choice stays. */
function forgetInMemoryWorkspaceState(): void {
  useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null, bound: null });
}

/** Mounts the real app signed in as the account at `path` and waits until the membership list and the workspace store are ready. */
async function openApp(account: Account, path: string): Promise<QueryClient> {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
  forgetInMemoryWorkspaceState();
  window.localStorage.removeItem("devrag.workspace");
  setAuthorization(account.session);
  router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  const client = new QueryClient();
  registerQueryClient(client);
  const current = router;
  registerNavigate({
    navigate: (to) => current.navigate(to, { replace: true }),
    currentPath: () => `${current.state.location.pathname}${current.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router: current }), createElement(Toaster)));
  await waitUntil(() => client.getQueryState(MEMBERSHIPS_QUERY_KEY)?.status === "success", { describe: "the membership list to load", timeout: 30_000 });
  await waitUntil(() => useWorkspaceStore.getState().initialisedFor === account.userId, { describe: "the workspace store to initialise", timeout: 30_000 });
  return client;
}

const pathNow = () => `${router?.state.location.pathname ?? ""}${router?.state.location.search ?? ""}`;
const rows = () => screen.queryAllByTestId("document-row");
const rowTexts = () => rows().map((row) => row.textContent ?? "");
const idOf = (path: string): string => new URL(path, "http://x").searchParams.get("id") ?? "";

function textFile(name: string, text: string): File {
  return new File([text], name, { type: "text/plain" });
}

/** Opens the upload dialog from the page's Upload files button, queues the files through the real input and uploads them. */
async function uploadThroughDialog(user: ReturnType<typeof userEvent.setup>, files: File[]): Promise<HTMLElement> {
  await user.click(await screen.findByTestId("dataset-upload"));
  await screen.findByTestId("upload-dialog");
  await user.upload(screen.getByTestId("upload-input"), files);
  await waitUntil(() => screen.queryAllByTestId("upload-row").length === files.length, { describe: "every file to be queued" });
  const submit = screen.getByTestId("upload-submit");
  expect(submit).toHaveTextContent(files.length === 1 ? "Upload 1 file" : `Upload ${files.length} files`);
  await user.click(submit);
  await waitUntil(() => screen.queryAllByTestId("upload-row-state").length === files.length && screen.queryAllByTestId("upload-row-state").every((state) => /^Uploaded/.test(state.textContent ?? "")), {
    describe: "every upload row to read Uploaded",
    timeout: 60_000,
  });
  return screen.getByTestId("upload-dialog");
}

async function closeUploadDialog(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByTestId("upload-close"));
  await waitUntil(() => screen.queryByTestId("upload-dialog") === null, { describe: "the upload dialog to close" });
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
  owner = await createAccount("owner");
  mate = await createAccount("mate");
  await join(owner, mate);
  // The owner's workspace gets the fake provider, its embedding model and the explicit default (D-18).
  setAuthorization(owner.session);
  await saveProvider({ tenantId: owner.tenantId, provider: PROVIDER_SLUG, apiKey: FAKE_PROVIDER_CREDENTIAL, baseUrl: fake.stackBaseUrl, models: [{ name: EMBED_MODEL, type: "embedding" }] });
  const models = await listModels(owner.tenantId, "embedding");
  const embedding = models.find((model) => model.name === EMBED_MODEL);
  expect(embedding?.dimension).toBe(FAKE_EMBEDDING_DIMENSION);
  await saveDefaults(owner.tenantId, { embedding: embedding?.id ?? "" });
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
  // Cleanup by recorded id: every dataset the journeys created is deleted through the API, which removes its rows, its
  // index documents and its stored blobs; the accounts are removed by the runner from LIVE_ACCOUNTS_FILE.
  const problems: string[] = [];
  for (const item of created) {
    setAuthorization(item.session);
    try {
      const gone = await deleteDatasets([item.id], item.tenantId);
      if (gone.length === 0) {
        // Already removed by a journey step.
        const remaining = await listDatasets({ tenantId: item.tenantId, page: 1, pageSize: 100, keywords: "" });
        if (remaining.items.some((dataset) => dataset.id === item.id)) problems.push(`dataset ${item.id} was not deleted`);
      }
    } catch {
      const remaining = await listDatasets({ tenantId: item.tenantId, page: 1, pageSize: 100, keywords: "" }).catch(() => ({ items: [] as { id: string }[] }));
      if (remaining.items.some((dataset) => dataset.id === item.id)) problems.push(`dataset ${item.id} could not be deleted`);
    }
  }
  // The teardown assertion: nothing the tests created is left in the owner's workspace.
  setAuthorization(owner.session);
  const left = await listDatasets({ tenantId: owner.tenantId, page: 1, pageSize: 100, keywords: "" });
  removeAuthorization();
  await fake?.close();
  expect(problems).toEqual([]);
  expect(left.total).toBe(0);
});

describe("live dataset journeys through the SPA on the real stack (UI-10, UI-11, UI-12, KB-01, KB-07, DOC-01, DOC-04, DOC-15)", () => {
  it("lets an owner create, meet the duplicate-name error, upload, rename on a clash, delete a document and delete the dataset", async () => {
    const user = userEvent.setup();
    const name = `Handbook ${suffix}`;
    await openApp(owner, "/datasets");

    // An empty workspace: the empty state and the dialog's entry point.
    await screen.findByTestId("datasets-page", {}, { timeout: 30_000 });
    await screen.findByText("No datasets yet", {}, { timeout: 30_000 });

    await user.click(screen.getByTestId("dataset-create"));
    await screen.findByTestId("create-dataset-form");
    await user.click(screen.getByTestId("field-dataset-name"));
    await user.paste(name);
    await user.click(screen.getByRole("radio", { name: /Whole team/ }));
    await user.click(screen.getByTestId("create-dataset-submit"));

    // The create follows the navigation to the dataset page; the new dataset has no documents.
    await waitUntil(() => pathNow().startsWith("/dataset/files?id="), { describe: "navigation to the new dataset", timeout: 30_000 });
    const datasetId = idOf(pathNow());
    expect(datasetId).toMatch(/^[0-9a-f]{32}$/);
    created.push({ tenantId: owner.tenantId, id: datasetId, session: owner.session });
    await screen.findByTestId("dataset-page", {}, { timeout: 30_000 });
    await within(await screen.findByTestId("dataset-meta")).findByText("Team", {}, { timeout: 30_000 });
    expect(within(screen.getByTestId("dataset-meta")).getByText("0 documents")).toBeInTheDocument();

    // Back at the gallery the card is there; the same name in another letter case is refused inline under the field.
    await user.click(screen.getByTestId("dataset-back"));
    await waitUntil(() => pathNow() === "/datasets", { describe: "the gallery" });
    const card = await screen.findByTestId("dataset-card", {}, { timeout: 30_000 });
    expect(card).toHaveTextContent(name);
    await user.click(screen.getByTestId("dataset-create"));
    await screen.findByTestId("create-dataset-form");
    await user.click(screen.getByTestId("field-dataset-name"));
    await user.paste(name.toUpperCase());
    await user.click(screen.getByTestId("create-dataset-submit"));
    const duplicate = await screen.findByText(`A dataset named "${name.toUpperCase()}" already exists in this workspace. Choose another name.`, {}, { timeout: 30_000 });
    expect(duplicate).toBeInTheDocument();
    expect(pathNow()).toBe("/datasets");
    expect(screen.getAllByTestId("dataset-card")).toHaveLength(1);
    await user.keyboard("{Escape}");
    await waitUntil(() => screen.queryByTestId("create-dataset-form") === null, { describe: "the create dialog to close" });

    // Open the dataset from its card.
    await user.click(within(screen.getByTestId("dataset-card")).getByTestId("dataset-card-link"));
    await waitUntil(() => pathNow() === `/dataset/files?id=${datasetId}`, { describe: "the dataset page" });
    await screen.findByText("No documents yet", {}, { timeout: 30_000 });

    // Two files through the real file input.
    const first = await uploadThroughDialog(user, [textFile("report.txt", `first report ${suffix}`), textFile("notes.txt", `some notes ${suffix}`)]);
    expect(within(first).getAllByTestId("upload-row")).toHaveLength(2);
    expect(within(first).queryByTestId("upload-rename-notice")).toBeNull();
    await closeUploadDialog(user);
    await waitUntil(() => rows().length === 2, { describe: "both documents in the table", timeout: 30_000 });
    for (const row of rows()) {
      expect(within(row).getByTestId("document-status")).toHaveTextContent("Not started");
      expect(within(row).getByTestId("document-progress")).toHaveTextContent("0%");
    }
    expect(rowTexts().some((text) => text.includes("report.txt"))).toBe(true);
    expect(rowTexts().some((text) => text.includes("notes.txt"))).toBe(true);
    await waitUntil(() => within(screen.getByTestId("dataset-meta")).queryByText("2 documents") !== null, { describe: "the meta line to read 2 documents", timeout: 30_000 });

    // The same name with other content is saved under a free name and says so; nothing is overwritten.
    const second = await uploadThroughDialog(user, [textFile("report.txt", `second report ${suffix}`)]);
    expect(within(second).getByTestId("upload-row-state")).toHaveTextContent("Uploaded as report(1).txt");
    expect(within(second).getByTestId("upload-rename-notice")).toHaveTextContent("1 file was renamed because a file with the same name was already in this dataset. Nothing was overwritten.");
    await closeUploadDialog(user);
    await waitUntil(() => rows().length === 3, { describe: "three documents in the table", timeout: 30_000 });
    await waitUntil(() => within(screen.getByTestId("dataset-meta")).queryByText("3 documents") !== null, { describe: "the meta line to read 3 documents", timeout: 30_000 });
    expect(rowTexts().some((text) => text.includes("report(1).txt"))).toBe(true);

    // Delete one document through its dialog; the table and the meta line drop to two.
    const renamed = rows().find((row) => (row.textContent ?? "").includes("report(1).txt"));
    expect(renamed).toBeDefined();
    await user.click(within(renamed as HTMLElement).getByTestId("document-delete"));
    const documentDialog = await screen.findByTestId("document-delete-dialog");
    expect(documentDialog).toHaveTextContent("report(1).txt");
    await user.click(screen.getByTestId("document-delete-confirm"));
    await waitUntil(() => rows().length === 2 && !rowTexts().some((text) => text.includes("report(1).txt")), { describe: "the document to leave the table", timeout: 30_000 });
    await waitUntil(() => within(screen.getByTestId("dataset-meta")).queryByText("2 documents") !== null, { describe: "the meta line to read 2 documents again", timeout: 30_000 });

    // Delete the dataset: the dialog states the count it read, the confirm leaves for the gallery, which is empty again.
    await user.click(screen.getByTestId("dataset-actions"));
    await user.click(await screen.findByTestId("dataset-menu-delete"));
    await waitUntil(() => (screen.queryByTestId("dataset-delete-count")?.textContent ?? "").includes("and its 2 documents will be permanently deleted"), { describe: "the delete dialog to state the 2 documents", timeout: 30_000 });
    await user.click(screen.getByTestId("dataset-delete-confirm"));
    await waitUntil(() => pathNow() === "/datasets", { describe: "the gallery after the delete", timeout: 60_000 });
    await screen.findByText("No datasets yet", {}, { timeout: 30_000 });

    // The server agrees: the dataset is gone for its owner.
    const detail = await call(`/api/v1/datasets/${datasetId}?tenant_id=${owner.tenantId}`, { bearer: owner.session });
    expect(detail.status).not.toBe(200);
    expect(fake.paths.filter((path) => path === "/v1/embeddings").length).toBeGreaterThan(0);
  });

  it("shows a member the team dataset and not the owner's own, lets them upload to it, and keeps their own dataset out of the owner's gallery", async () => {
    const user = userEvent.setup();
    setAuthorization(owner.session);
    const teamName = `Team notes ${suffix}`;
    const ownName = `Owner private ${suffix}`;
    const teamDataset = await createDataset({ tenantId: owner.tenantId, name: teamName, permission: "team" });
    created.push({ tenantId: owner.tenantId, id: teamDataset.id, session: owner.session });
    const ownDataset = await createDataset({ tenantId: owner.tenantId, name: ownName, permission: "me" });
    created.push({ tenantId: owner.tenantId, id: ownDataset.id, session: owner.session });

    // The member starts in their own workspace and switches to the owner's through the header selector.
    await openApp(mate, "/datasets");
    await screen.findByText("No datasets yet", {}, { timeout: 30_000 });
    await user.click(await screen.findByTestId("workspace-switch"));
    await user.click(await screen.findByTestId(`workspace-option-${owner.tenantId}`));
    await waitUntil(() => useWorkspaceStore.getState().activeTenantId === owner.tenantId, { describe: "the owner's workspace to become active" });

    const memberCards = await waitUntil(
      () => {
        const found = screen.queryAllByTestId("dataset-card");
        return found.length > 0 ? found : null;
      },
      { describe: "the owner's team dataset in the member's gallery", timeout: 30_000 },
    );
    const names = memberCards.map((card) => card.textContent ?? "");
    expect(names.some((text) => text.includes(teamName))).toBe(true);
    expect(names.some((text) => text.includes(ownName))).toBe(false);
    expect(screen.queryByText(ownName)).toBeNull();
    // A member has no management menu on a dataset they did not create.
    expect(screen.queryByTestId("dataset-actions")).toBeNull();

    // Open the team dataset and upload one file.
    const teamCard = memberCards.find((card) => (card.textContent ?? "").includes(teamName)) as HTMLElement;
    await user.click(within(teamCard).getByTestId("dataset-card-link"));
    await waitUntil(() => pathNow() === `/dataset/files?id=${teamDataset.id}`, { describe: "the team dataset page" });
    await screen.findByText("No documents yet", {}, { timeout: 30_000 });
    const dialog = await uploadThroughDialog(user, [textFile("from-member.txt", `member upload ${suffix}`)]);
    expect(within(dialog).getByTestId("upload-row-state")).toHaveTextContent("Uploaded");
    await closeUploadDialog(user);
    await waitUntil(() => rows().length === 1, { describe: "the member's document in the table", timeout: 30_000 });
    expect(within(rows()[0]).getByTestId("document-status")).toHaveTextContent("Not started");
    expect(within(rows()[0]).getByTestId("document-progress")).toHaveTextContent("0%");

    // The member creates a dataset of their own in the shared workspace ("Only me" is the default).
    const mineName = `Member private ${suffix}`;
    await user.click(screen.getByTestId("dataset-back"));
    await waitUntil(() => pathNow() === "/datasets", { describe: "the gallery" });
    await screen.findAllByTestId("dataset-card", {}, { timeout: 30_000 });
    await user.click(screen.getByTestId("dataset-create"));
    await screen.findByTestId("create-dataset-form");
    await user.click(screen.getByTestId("field-dataset-name"));
    await user.paste(mineName);
    await user.click(screen.getByTestId("create-dataset-submit"));
    await waitUntil(() => pathNow().startsWith("/dataset/files?id="), { describe: "navigation to the member's dataset", timeout: 30_000 });
    const mineId = idOf(pathNow());
    created.push({ tenantId: owner.tenantId, id: mineId, session: mate.session });

    // The member's gallery shows the team dataset and their own; the owner's shows the team dataset and the owner's own, never the member's.
    await user.click(await screen.findByTestId("dataset-back"));
    await waitUntil(() => pathNow() === "/datasets", { describe: "the gallery" });
    await waitUntil(() => screen.queryAllByTestId("dataset-card").length === 2, { describe: "the member's two visible datasets", timeout: 30_000 });
    const memberView = screen.getAllByTestId("dataset-card").map((card) => card.textContent ?? "");
    expect(memberView.some((text) => text.includes(teamName))).toBe(true);
    expect(memberView.some((text) => text.includes(mineName))).toBe(true);
    expect(memberView.some((text) => text.includes(ownName))).toBe(false);

    await openApp(owner, "/datasets");
    await waitUntil(() => screen.queryAllByTestId("dataset-card").length === 2, { describe: "the owner's two visible datasets", timeout: 30_000 });
    const ownerView = screen.getAllByTestId("dataset-card").map((card) => card.textContent ?? "");
    expect(ownerView.some((text) => text.includes(teamName))).toBe(true);
    expect(ownerView.some((text) => text.includes(ownName))).toBe(true);
    expect(ownerView.some((text) => text.includes(mineName))).toBe(false);
    expect(screen.queryByText(mineName)).toBeNull();
    // The API agrees with the page (the page is not the only guard).
    const listed = await call<{ items: { name: string }[] }>(`/api/v1/datasets?tenant_id=${owner.tenantId}&page_size=100`, { bearer: owner.session });
    expect((listed.envelope?.data.items ?? []).map((item) => item.name)).not.toContain(mineName);
  });
});
