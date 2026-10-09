import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, configure, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { containsKeyFragment, endsWithKeyTail, liveProviderKey } from "@/test/live/provider-key";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, removeAuthorization, setAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL) with the real SPA routes, the real HTTP client and the real provider
// routes, which test the key with real calls to OpenRouter from the app container (D-01, D-29; the browser tier uses the
// user's key like the Python live tier does, see the 03-22 SUMMARY). No request is mocked and the HTTP client is the
// application's own. The key is read by `liveProviderKey`, typed into the dialog like a user would, and never printed: every
// assertion about it is a boolean, and the testing-library DOM dump (which would include a password input's value) is
// switched off for this file.
//
// Call budget (D-05): a provider save tests each given model with one real call. This file makes three saves of one
// chat model and one embedding model, one of one chat model and one of one chat model: about five real calls. The
// provider-test limit is 10 saves per 300 s per workspace and every run uses its own fresh accounts.
const PASSWORD = ["live", "models", "pass", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const CHAT_MODEL = process.env.LIVE_CHAT_MODEL ?? "meta-llama/llama-3.1-8b-instruct";
const EMBED_MODEL = process.env.LIVE_EMBED_MODEL ?? "baai/bge-m3";
const EXPECTED_DIM = Number(process.env.LIVE_EXPECTED_DIM ?? "1024");
const PAGE = "/user-setting/model";
// A made-up key, assembled from parts so no scanner sees a key-shaped literal.
const BAD_KEY = ["made", "up", "key", "for", "the", "refusal", "case", suffix].join("-");

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
  tenantName: string;
}

let key = "";
let owner: Account;
let mate: Account;
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
  const email = `webmodels-${tag}-${suffix}@example.test`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: PASSWORD, nickname: `webmodels-${tag}-${suffix}` } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: PASSWORD } });
  const session = login.envelope?.code === 0 ? login.envelope.data?.token : undefined;
  if (!session) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  const info = await call<{ id: string; tenant_id: string; tenant_name: string }>("/v1/user/info", { bearer: session });
  const data = info.envelope?.data;
  if (!data?.tenant_id || !data.id) throw new Error(`reading ${tag} returned HTTP ${info.status}`);
  return { email, session, userId: data.id, tenantId: data.tenant_id, tenantName: data.tenant_name };
}

async function join(workspaceOwner: Account, teammate: Account): Promise<void> {
  const invited = await call(`/api/v1/tenants/${workspaceOwner.tenantId}/users`, { method: "POST", bearer: workspaceOwner.session, body: { email: teammate.email } });
  expect(invited.status).toBe(200);
  const accepted = await call(`/api/v1/tenants/${workspaceOwner.tenantId}`, { method: "PATCH", bearer: teammate.session, body: { action: "accept" } });
  expect(accepted.status).toBe(200);
}

/** A page reload: the in-memory workspace state is gone, the stored choice stays. */
function forgetInMemoryWorkspaceState(): void {
  useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null });
}

/** Mounts the real app signed in as the account on the Models page and waits until the page and its membership list have loaded. */
async function openModels(account: Account): Promise<void> {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
  forgetInMemoryWorkspaceState();
  setAuthorization(account.session);
  router = createMemoryRouter(buildRoutes(), { initialEntries: [PAGE] });
  const client = new QueryClient();
  registerQueryClient(client);
  const current = router;
  registerNavigate({
    navigate: (to) => current.navigate(to, { replace: true }),
    currentPath: () => `${current.state.location.pathname}${current.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router: current }), createElement(Toaster)));
  await screen.findByTestId("models-page", {}, { timeout: 30_000 });
  await waitUntil(() => client.getQueryState(MEMBERSHIPS_QUERY_KEY)?.status === "success" && client.isFetching() === 0, { describe: "the page data to load", timeout: 30_000 });
  await waitUntil(() => useWorkspaceStore.getState().initialisedFor === account.userId, { describe: "the workspace store to initialise", timeout: 30_000 });
}

const page = () => screen.getByTestId("models-page");
const openrouterRow = () => within(page()).getByTestId("provider-row-openrouter");
const selectValue = (testId: string) => (screen.getByTestId(testId) as HTMLSelectElement).value;

/** Types into a field the way a user does: click, then paste (the key is one paste, not 70 key events). */
async function fill(user: ReturnType<typeof userEvent.setup>, testId: string, value: string): Promise<void> {
  await user.click(screen.getByTestId(testId));
  await user.paste(value);
}

beforeAll(async () => {
  // A failed query would otherwise print the DOM, and a password input's value is part of the DOM.
  configure({ getElementError: (message) => new Error(message ?? "element not found") });
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
  key = liveProviderKey();
  await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  owner = await createAccount("owner");
  mate = await createAccount("mate");
  await join(owner, mate);
});
afterEach(() => {
  cleanup();
  registerNavigate(null);
  removeAuthorization();
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("live Models page through the SPA and the real provider (UI-37, TEN-12, TEN-13, D-18)", () => {
  it("sets up OpenRouter through the dialog, shows the mask ending in the key's tail, and keeps explicit defaults across a fresh render", async () => {
    const user = userEvent.setup();
    await openModels(owner);

    // Nothing is chosen and nothing is guessed: before a provider exists both selects are disabled on 'Not set'.
    expect(within(openrouterRow()).getByTestId("provider-status")).toHaveTextContent("Not configured");
    expect(screen.getByTestId("default-chat")).toBeDisabled();
    expect(screen.getByTestId("default-embedding")).toBeDisabled();
    expect(screen.getByText("Add a provider with a chat model first.")).toBeInTheDocument();
    expect(screen.getByText("Add a provider with an embedding model first.")).toBeInTheDocument();

    await user.click(within(openrouterRow()).getByTestId("provider-setup"));
    await screen.findByTestId("provider-dialog");
    await fill(user, "field-provider-key", key);
    await fill(user, "field-chat-model", CHAT_MODEL);
    await fill(user, "field-embedding-model", EMBED_MODEL);
    await user.click(screen.getByTestId("provider-submit"));

    await waitUntil(() => within(openrouterRow()).getByTestId("provider-status").textContent === "Configured", { describe: "OpenRouter to show Configured", timeout: 60_000 });
    await waitUntil(() => screen.queryByTestId("provider-dialog") === null, { describe: "the dialog to close", timeout: 15_000 });
    const mask = await within(openrouterRow()).findByTestId("provider-mask", {}, { timeout: 30_000 });
    expect(endsWithKeyTail(mask.textContent ?? "", key)).toBe(true);
    expect(mask.textContent ?? "").toContain("•");
    const modelRows = await waitUntil(
      () => {
        const rows = within(openrouterRow()).queryAllByTestId("model-row");
        return rows.length === 2 ? rows : null;
      },
      { describe: "both models to be listed", timeout: 30_000 },
    );
    expect(modelRows.map((row) => row.textContent ?? "").some((text) => text.includes(CHAT_MODEL) && text.includes("Chat"))).toBe(true);
    expect(modelRows.map((row) => row.textContent ?? "").some((text) => text.includes(EMBED_MODEL) && text.includes(`${EXPECTED_DIM} dimensions`))).toBe(true);

    // The key is nowhere on the page: not as text, not as an attribute.
    expect(containsKeyFragment(document.body.innerHTML, key)).toBe(false);

    // Defaults are an explicit choice: both start on 'Not set' although models now exist.
    await waitUntil(() => !(screen.getByTestId("default-chat") as HTMLSelectElement).disabled, { describe: "the defaults selects to enable", timeout: 30_000 });
    expect(selectValue("default-chat")).toBe("");
    expect(selectValue("default-embedding")).toBe("");
    expect(screen.getByTestId("defaults-submit")).toHaveAttribute("aria-disabled", "true");

    const option = (testId: string, name: string): string => {
      const found = Array.from((screen.getByTestId(testId) as HTMLSelectElement).options).find((o) => o.textContent === name);
      return found?.value ?? "";
    };
    const chatId = option("default-chat", CHAT_MODEL);
    const embedId = option("default-embedding", EMBED_MODEL);
    expect(chatId).not.toBe("");
    expect(embedId).not.toBe("");
    await user.selectOptions(screen.getByTestId("default-chat"), chatId);
    await user.selectOptions(screen.getByTestId("default-embedding"), embedId);
    await user.click(screen.getByTestId("defaults-submit"));
    await screen.findByText("Default models saved", {}, { timeout: 30_000 });

    // A fresh tree reads the defaults from the server.
    await openModels(owner);
    await waitUntil(() => selectValue("default-chat") === chatId && selectValue("default-embedding") === embedId, { describe: "the saved defaults to be selected again", timeout: 30_000 });
    expect(within(openrouterRow()).getByText("Default chat")).toBeInTheDocument();
    expect(within(openrouterRow()).getByText("Default embedding")).toBeInTheDocument();

    // The server holds the same explicit choice.
    const held = await call<{ chat: string; embedding: string }>(`/api/v1/models/default?tenant_id=${owner.tenantId}`, { bearer: owner.session });
    expect(held.envelope?.data).toEqual({ chat: chatId, embedding: embedId });
  });

  it("shows the provider's refusal of a bad key inline and keeps the session, the page and the saved provider", async () => {
    const user = userEvent.setup();
    await openModels(owner);
    const tokenBefore = getAuthorization();
    expect(tokenBefore).toBe(owner.session);
    const maskBefore = (await within(openrouterRow()).findByTestId("provider-mask", {}, { timeout: 30_000 })).textContent;

    await user.click(within(openrouterRow()).getByTestId("provider-change"));
    await screen.findByTestId("provider-dialog");
    expect(screen.queryByTestId("field-chat-model")).toBeNull();
    await fill(user, "field-provider-key", BAD_KEY);
    await user.click(screen.getByTestId("provider-submit"));

    const refusal = await screen.findByTestId("provider-refusal", {}, { timeout: 60_000 });
    expect(refusal.textContent ?? "").toContain("OpenRouter refused this configuration");
    expect((refusal.textContent ?? "").length).toBeGreaterThan("OpenRouter refused this configuration".length);
    expect(containsKeyFragment(refusal.textContent ?? "", BAD_KEY)).toBe(false);

    // Still on the page, still signed in with the same token, and no session toast of any kind.
    expect(router?.state.location.pathname).toBe(PAGE);
    expect(getAuthorization()).toBe(tokenBefore);
    expect(screen.getByTestId("provider-dialog")).toBeInTheDocument();
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();

    // Nothing was stored: the row, after the refetch, still shows the old mask.
    await user.click(within(screen.getByTestId("provider-dialog")).getByRole("button", { name: "Close" }));
    await waitUntil(() => screen.queryByTestId("provider-dialog") === null, { describe: "the dialog to close", timeout: 15_000 });
    expect(within(openrouterRow()).getByTestId("provider-mask").textContent).toBe(maskBefore);
    expect(within(openrouterRow()).getAllByTestId("model-row")).toHaveLength(2);
    expect(router?.state.location.pathname).toBe(PAGE);
    expect(getAuthorization()).toBe(tokenBefore);

    // The session still works against the server.
    const info = await call("/v1/user/info", { bearer: owner.session });
    expect(info.status).toBe(200);
  });

  it("changes the key again with a valid key: the dialog closes, the mask ends in the key's tail and both models and both defaults stay", async () => {
    const user = userEvent.setup();
    await openModels(owner);
    await user.click(within(openrouterRow()).getByTestId("provider-change"));
    await screen.findByTestId("provider-dialog");
    expect(screen.queryByTestId("field-chat-model")).toBeNull();
    expect(screen.queryByTestId("field-embedding-model")).toBeNull();
    await fill(user, "field-provider-key", key);
    await user.click(screen.getByTestId("provider-submit"));

    await waitUntil(() => screen.queryByTestId("provider-dialog") === null, { describe: "the dialog to close after a passing test", timeout: 60_000 });
    await screen.findByText("OpenRouter updated", {}, { timeout: 15_000 });
    const mask = await within(openrouterRow()).findByTestId("provider-mask", {}, { timeout: 30_000 });
    expect(endsWithKeyTail(mask.textContent ?? "", key)).toBe(true);
    await waitUntil(() => within(openrouterRow()).queryAllByTestId("model-row").length === 2, { describe: "both models to stay listed", timeout: 30_000 });
    expect(within(openrouterRow()).getByText("Default chat")).toBeInTheDocument();
    expect(within(openrouterRow()).getByText("Default embedding")).toBeInTheDocument();
    expect(containsKeyFragment(document.body.innerHTML, key)).toBe(false);

    const models = await call<Array<{ name: string; type: string; dimension: number | null }>>(`/api/v1/models?tenant_id=${owner.tenantId}`, { bearer: owner.session });
    const rows = models.envelope?.data ?? [];
    expect(rows.some((m) => m.name === CHAT_MODEL && m.type === "chat")).toBe(true);
    expect(rows.some((m) => m.name === EMBED_MODEL && m.type === "embedding" && m.dimension === EXPECTED_DIM)).toBe(true);
  });

  it("shows a member of the joined workspace the read-only page: no mask, no address, defaults as plain text, no action button", async () => {
    await openModels(mate);
    useWorkspaceStore.getState().setActive(owner.tenantId);

    const notice = await screen.findByTestId("models-readonly-notice", {}, { timeout: 30_000 });
    expect(notice).toHaveTextContent("Only the workspace owner and admins can change model settings.");
    const row = await waitUntil(() => within(page()).queryByTestId("provider-row-openrouter"), { describe: "the owner's configured provider", timeout: 30_000 });
    await waitUntil(() => within(row).queryAllByTestId("model-row").length === 2, { describe: "the owner's models", timeout: 30_000 });
    expect(within(page()).queryByTestId("provider-mask")).toBeNull();
    const html = page().innerHTML;
    expect(html).not.toContain("openrouter.ai");
    expect(containsKeyFragment(html, key)).toBe(false);

    // The defaults are a definition list of plain text; nothing to edit.
    const chatTerm = await within(page()).findByText("Default chat model", {}, { timeout: 30_000 });
    expect(chatTerm.tagName).toBe("DT");
    await waitUntil(() => (chatTerm.nextElementSibling?.textContent ?? "").includes(CHAT_MODEL), { describe: "the chat default as text", timeout: 30_000 });
    const embeddingTerm = within(page()).getByText("Default embedding model");
    expect(embeddingTerm.nextElementSibling?.textContent ?? "").toContain(EMBED_MODEL);
    expect(within(page()).queryByTestId("defaults-form")).toBeNull();
    expect(within(page()).queryAllByRole("combobox")).toHaveLength(0);
    expect(within(page()).queryAllByRole("button")).toHaveLength(0);
  });
});
