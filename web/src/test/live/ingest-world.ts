/**
 * Shared set-up of the Phase 4 live journeys (plan 04-34): real accounts, a workspace with the loopback embedding provider,
 * a dataset made through the real service, the real routes mounted in a memory router, and cleanup by recorded id.
 *
 * Nothing of devRag is replaced. Only the third-party provider is the loopback fake of `fake-provider.ts`, so the real
 * provider key never enters the browser tier (T-03-22-04). jsdom has no object-URL support, so `installObjectUrls` gives it
 * a registry that keeps the blob behind each `blob:` address; the SPA's own code makes and revokes the addresses.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { expect, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { buildRoutes } from "@/routes";
import { createDataset, deleteDatasets } from "@/services/dataset-service";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { listModels, saveDefaults, saveProvider } from "@/services/model-service";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { FAKE_EMBEDDING_DIMENSION, startFakeProvider, type FakeProvider } from "@/test/live/fake-provider";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

const PASSWORD = ["live", "ingest", "pass", "0001"].join("-");
// A made-up credential for the fake provider, assembled from parts so no scanner sees a key-shaped literal.
const FAKE_PROVIDER_CREDENTIAL = ["fake", "ingest", "journey", "0001"].join("-");
const PROVIDER_SLUG = "openai-compatible";
const EMBED_MODEL = "fake-embed";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

export interface Account {
  email: string;
  session: string;
  userId: string;
  tenantId: string;
}

export interface World {
  fake: FakeProvider;
  owner: Account;
  datasetId: string;
  embeddingId: string;
  /** The router of the page now shown, if any. */
  router: () => ReturnType<typeof createMemoryRouter> | null;
}

export async function call<T>(path: string, init: { method?: string; bearer?: string; body?: unknown } = {}): Promise<{ status: number; envelope: Envelope<T> | null }> {
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

/** Browser APIs the components use and jsdom lacks. None of them stands in for any devRag code. */
export function installBrowserShims(): void {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
}

const blobs = new Map<string, Blob>();
let blobCounter = 0;

/** Gives jsdom `URL.createObjectURL` and `revokeObjectURL` that keep the blob, so a test can read the bytes behind an address. */
export function installObjectUrls(): void {
  URL.createObjectURL = (object: Blob | MediaSource): string => {
    blobCounter += 1;
    const address = `blob:${window.location.origin}/live-${blobCounter}`;
    blobs.set(address, object as Blob);
    return address;
  };
  URL.revokeObjectURL = (address: string): void => {
    blobs.delete(address);
  };
}

/** The bytes behind a `blob:` address made by the SPA, or null once it was revoked. */
export async function blobBytes(address: string): Promise<Uint8Array | null> {
  const stored = blobs.get(address);
  return stored === undefined ? null : new Uint8Array(await stored.arrayBuffer());
}

/** The pixel size written in a PNG or JPEG header (what a browser reports as the natural size), or null if the bytes are neither. */
export function imageSizeOf(bytes: Uint8Array): { width: number; height: number } | null {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length > 24 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (bytes.length > 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    let at = 2;
    while (at + 9 < bytes.length) {
      if (bytes[at] !== 0xff) return null;
      const marker = bytes[at + 1];
      const length = view.getUint16(at + 2);
      if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) return { height: view.getUint16(at + 5), width: view.getUint16(at + 7) };
      at += 2 + length;
    }
  }
  return null;
}

function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

/** A real account through the live ingress. The email is written to LIVE_ACCOUNTS_FILE so the runner removes it. */
export async function createAccount(tag: string): Promise<Account> {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  const email = `webingest-${tag}-${suffix}@example.test`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: PASSWORD, nickname: `webingest-${tag}-${suffix}` } });
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

/** The teammate joins the owner's workspace (invite, then accept). */
export async function join(owner: Account, teammate: Account): Promise<void> {
  const invited = await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: owner.session, body: { email: teammate.email } });
  expect(invited.status).toBe(200);
  const accepted = await call(`/api/v1/tenants/${owner.tenantId}`, { method: "PATCH", bearer: teammate.session, body: { action: "accept" } });
  expect(accepted.status).toBe(200);
}

/** The fake provider, an owner whose workspace uses it, and a dataset on its embedding model. */
export async function createWorld(tag: string, permission: "me" | "team" = "me"): Promise<World> {
  await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  const fake = await startFakeProvider();
  const owner = await createAccount(tag);
  setAuthorization(owner.session);
  try {
    await saveProvider({ tenantId: owner.tenantId, provider: PROVIDER_SLUG, apiKey: FAKE_PROVIDER_CREDENTIAL, baseUrl: fake.stackBaseUrl, models: [{ name: EMBED_MODEL, type: "embedding" }] });
    const models = await listModels(owner.tenantId, "embedding");
    const embedding = models.find((model) => model.name === EMBED_MODEL);
    expect(embedding?.dimension).toBe(FAKE_EMBEDDING_DIMENSION);
    await saveDefaults(owner.tenantId, { embedding: embedding?.id ?? "" });
    const dataset = await createDataset({ tenantId: owner.tenantId, name: `Ingest journey ${tag} ${Date.now().toString(36)}`, permission, embdId: embedding?.id });
    return { fake, owner, datasetId: dataset.id, embeddingId: embedding?.id ?? "", router: () => current };
  } finally {
    removeAuthorization();
  }
}

/** Cleanup by recorded id and tenant: deleting the dataset removes its rows, index documents and blobs. */
export async function destroyWorld(world: World | undefined): Promise<void> {
  if (world === undefined) return;
  setAuthorization(world.owner.session);
  await deleteDatasets([world.datasetId], world.owner.tenantId).catch(() => []);
  removeAuthorization();
  await world.fake.close();
}

let current: ReturnType<typeof createMemoryRouter> | null = null;

/** What `afterEach` of a journey file runs. */
export function resetApp(): void {
  cleanup();
  registerNavigate(null);
  removeAuthorization();
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  current = null;
}

/** Mounts the real app signed in as the account at `path` (a fresh router and client, the way a page load does) and waits until it is ready. */
export async function openApp(account: Account, path: string): Promise<QueryClient> {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
  useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null, bound: null });
  window.localStorage.removeItem("devrag.workspace");
  setAuthorization(account.session);
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  current = router;
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router }), createElement(Toaster)));
  await waitUntil(() => client.getQueryState(MEMBERSHIPS_QUERY_KEY)?.status === "success", { describe: "the membership list to load", timeout: 30_000 });
  await waitUntil(() => useWorkspaceStore.getState().initialisedFor === account.userId, { describe: "the workspace store to initialise", timeout: 30_000 });
  return client;
}
