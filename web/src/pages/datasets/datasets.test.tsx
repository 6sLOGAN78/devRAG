import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import DatasetsPage from ".";

// Drives the real page, hooks, services and HTTP client against an in-memory server shaped like plans 03-13 and 03-14:
// the paged dataset list (tenant scoped, keyword filtered), the workspace defaults, the models and the membership list.
const OWNER: SessionUser = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};

const EMBED = "embed-one@OpenRouter";

interface Row {
  tenant_id: string;
  tenant_name: string;
  owner_nickname: string;
  owner_avatar: string;
  role: string;
  joined_time: string;
}
const OWN: Row = { tenant_id: "t1", tenant_name: "Ada's workspace", owner_nickname: "Ada", owner_avatar: "", role: "owner", joined_time: "2026-10-01T12:00:00Z" };
const joined = (role: string): Row => ({ tenant_id: "t9", tenant_name: "Grace's workspace", owner_nickname: "Grace", owner_avatar: "", role, joined_time: "2026-10-01T12:00:00Z" });
const stored = (rows: readonly Row[]) =>
  rows.map((r) => ({ tenantId: r.tenant_id, tenantName: r.tenant_name, ownerNickname: r.owner_nickname, ownerAvatar: r.owner_avatar, role: r.role, joinedTime: r.joined_time }));

interface Dataset {
  id: string;
  name: string;
  description: string;
  permission: string;
  embd_id: string;
  embedding_dimension: number;
  doc_num: number;
  created_by: string;
  tenant_id: string;
  update_time: number;
}
const UPDATED = Date.UTC(2026, 9, 5, 12, 0, 0);
const dataset = (n: number, over: Partial<Dataset> = {}, tenant = "t1"): Dataset => ({
  id: `ds-${tenant}-${n}`,
  name: `Dataset ${String(n).padStart(2, "0")}`,
  description: `About dataset ${n}`,
  permission: "me",
  embd_id: EMBED,
  embedding_dimension: 8,
  doc_num: n,
  created_by: "u1",
  tenant_id: tenant,
  update_time: UPDATED,
  ...over,
});
const many = (count: number, tenant = "t1") => Array.from({ length: count }, (_, i) => dataset(i + 1, {}, tenant));

interface Forced {
  status: number;
  message: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let memberships: Row[] = [];
let forced: Record<string, Forced> = {};
let hold: Promise<void> | null = null;
let byTenant: Record<string, Dataset[]> = {};
let defaultsByTenant: Record<string, { chat: string; embedding: string }> = {};

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const response = { data: { code: f.status, message: f.message, data: null }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const paramsOf = (config: InternalAxiosRequestConfig) => (config.params ?? {}) as Record<string, string | number>;

function serve(config: InternalAxiosRequestConfig): unknown {
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  const stop = forced[key];
  if (stop) return failure(config, stop);
  const params = paramsOf(config);
  const tenant = String(params.tenant_id ?? "");
  if (key === "GET /v1/tenant/list") return ok(config, memberships);
  if (key === "GET /api/v1/datasets") {
    const keywords = String(params.keywords ?? "").toLowerCase();
    const matching = (byTenant[tenant] ?? []).filter((d) => d.name.toLowerCase().includes(keywords));
    const size = Number(params.page_size);
    const page = Number(params.page);
    return ok(config, { items: matching.slice((page - 1) * size, page * size), total: matching.length });
  }
  if (key === "GET /api/v1/models") {
    const wanted = defaultsByTenant[tenant]?.embedding ?? "";
    const list = wanted === "" ? [] : [{ id: wanted, name: wanted.split("@")[0], provider: wanted.split("@")[1], type: "embedding", dimension: 8, max_tokens: 8192, instance: "default", used_tokens: 0 }];
    return ok(config, list);
  }
  if (key === "GET /api/v1/models/default") return ok(config, defaultsByTenant[tenant] ?? { chat: "", embedding: "" });
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (hold && config.url === "/api/v1/datasets") await hold;
  return (await Promise.resolve(serve(config))) as never;
};

const listCalls = () => calls.filter((c) => c.url === "/api/v1/datasets" && c.method?.toUpperCase() === "GET");

function Probe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderPage(entry = "/datasets") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <DatasetsPage />
        <Probe />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const search = () => new URLSearchParams(screen.getByTestId("location").textContent?.split("?")[1] ?? "");
const cards = () => screen.queryAllByTestId("dataset-card");

beforeEach(() => {
  calls = [];
  forced = {};
  hold = null;
  memberships = [OWN];
  byTenant = { t1: many(3), t9: many(2, "t9") };
  defaultsByTenant = { t1: { chat: "", embedding: EMBED }, t9: { chat: "", embedding: EMBED } };
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  useWorkspaceStore.getState().initialise("u1", "t1", stored([OWN]));
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  vi.useRealTimers();
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Datasets gallery structure (UI-10)", () => {
  it("makes Datasets the first heading, sets the title and names the workspace in the helper line", async () => {
    renderPage();
    const page = screen.getByTestId("datasets-page");
    expect(within(page).getByRole("heading", { level: 1, name: "Datasets" })).toBe(within(page).getAllByRole("heading")[0]);
    expect(document.title).toBe("Datasets - devRag");
    expect(within(page).getByText("Datasets in Ada's workspace. You see the ones you created and the ones shared with the team.")).toBeInTheDocument();
    await screen.findByTestId("dataset-grid");
  });

  it("shows eight skeleton cards while loading, then the cards in a 1/2/3/4 column grid", async () => {
    let release: () => void = () => {};
    hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderPage();
    expect(await screen.findAllByTestId("dataset-card-skeleton")).toHaveLength(8);
    expect(screen.getByText("Loading datasets")).toBeInTheDocument();
    release();
    const grid = await screen.findByTestId("dataset-grid");
    expect(screen.queryAllByTestId("dataset-card-skeleton")).toHaveLength(0);
    for (const token of ["grid", "gap-6", "sm:grid-cols-2", "lg:grid-cols-3", "xl:grid-cols-4"]) expect(grid.className.split(" ")).toContain(token);
    expect(cards()).toHaveLength(3);
  });

  it("draws each card as an article with one name link covering it, a two-line description, the badge and the meta line", async () => {
    byTenant.t1 = [
      dataset(1, { name: "Alpha", description: "First description", permission: "team", doc_num: 3 }),
      dataset(2, { name: "Beta", description: "", permission: "me", doc_num: 1 }),
    ];
    renderPage();
    await screen.findByTestId("dataset-grid");
    const [alpha, beta] = cards() as [HTMLElement, HTMLElement];
    expect(alpha.tagName).toBe("ARTICLE");
    const link = within(alpha).getByTestId("dataset-card-link");
    expect(link).toHaveAttribute("href", "/dataset/files?id=ds-t1-1");
    expect(link).toHaveTextContent("Alpha");
    expect(link.className).toContain("after:absolute");
    expect(link.className).toContain("after:inset-0");
    expect(alpha.className).toContain("relative");
    expect(alpha.className).toContain("min-h-40");
    expect(within(alpha).getAllByRole("link")).toHaveLength(1);
    expect(within(alpha).getByText("First description").className).toContain("line-clamp-2");
    expect(within(alpha).getByText("Team")).toBeInTheDocument();
    expect(within(alpha).getByText("3 documents")).toBeInTheDocument();
    const date = new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(UPDATED));
    expect(within(alpha).getByText(`Updated ${date}`)).toBeInTheDocument();
    expect(within(beta).getByText("Only me")).toBeInTheDocument();
    expect(within(beta).getByText("1 document")).toBeInTheDocument();
    expect(beta.querySelectorAll("p.line-clamp-2")).toHaveLength(0);
    expect(within(alpha).queryByRole("button")).toBeNull();
  });

  it("renders dataset names and descriptions as text, never as markup", async () => {
    byTenant.t1 = [dataset(1, { name: "<img src=x onerror=alert(1)>", description: "<b>bold</b> <script>alert(1)</script>" })];
    renderPage();
    const grid = await screen.findByTestId("dataset-grid");
    expect(grid.querySelector("img, b, script")).toBeNull();
    expect(within(grid).getByTestId("dataset-card-link")).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(within(grid).getByText("<b>bold</b> <script>alert(1)</script>")).toBeInTheDocument();
  });

  it("sends the active tenant id, page size 12 and no keywords on the first request", async () => {
    renderPage();
    await screen.findByTestId("dataset-grid");
    expect(listCalls()[0]?.params).toEqual({ tenant_id: "t1", page: 1, page_size: 12 });
  });
});

describe("States (UI-SPEC)", () => {
  it("shows 'No datasets yet' with a Create dataset action and hides the header action and the toolbar", async () => {
    byTenant.t1 = [];
    renderPage();
    expect(await screen.findByRole("heading", { level: 2, name: "No datasets yet" })).toBeInTheDocument();
    expect(screen.getByText("A dataset holds the documents you want to search and ask questions about. Create one, then upload files into it.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create dataset" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Create dataset" })).toBe(screen.getByTestId("dataset-create"));
    expect(screen.queryByTestId("datasets-search")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("shows the header action and the toolbar once datasets exist", async () => {
    renderPage();
    await screen.findByTestId("dataset-grid");
    expect(screen.getAllByRole("button", { name: "Create dataset" })).toHaveLength(1);
    expect(screen.getByRole("searchbox", { name: "Search datasets" })).toBeInTheDocument();
  });

  it("shows 'No datasets match' with Clear search that clears keywords, and keeps the toolbar and header action", async () => {
    renderPage("/datasets?keywords=zzz");
    expect(await screen.findByRole("heading", { level: 2, name: 'No datasets match "zzz"' })).toBeInTheDocument();
    expect(screen.getByText("Check the spelling or try a shorter search.")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search datasets" })).toHaveValue("zzz");
    expect(screen.getByTestId("dataset-create")).toBeInTheDocument();
    const empty = screen.getByTestId("empty-state");
    await userEvent.click(within(empty).getByRole("button", { name: "Clear search" }));
    await waitFor(() => expect(search().has("keywords")).toBe(false));
    expect(await screen.findByTestId("dataset-grid")).toBeInTheDocument();
  });

  it("shows an in-place error with Try again that refetches", async () => {
    forced["GET /api/v1/datasets"] = { status: 503, message: "down" };
    renderPage();
    const state = await screen.findByTestId("error-state");
    expect(within(state).getByRole("heading", { name: "Couldn't load datasets" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Datasets" })).toBeInTheDocument();
    delete forced["GET /api/v1/datasets"];
    await userEvent.click(within(state).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("dataset-grid")).toBeInTheDocument();
  });
});

describe("Paging and search in the URL (KB-04)", () => {
  beforeEach(() => {
    byTenant.t1 = many(25);
  });

  it("pages 12 at a time with previous and next, keeping the page in the URL", async () => {
    renderPage();
    await screen.findByTestId("dataset-grid");
    expect(cards()).toHaveLength(12);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(search().get("page")).toBe("2"));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(search().get("page")).toBe("2"));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(search().has("page")).toBe(false));
  });

  it("steps back to the last page when the requested page is past the end", async () => {
    renderPage("/datasets?page=9");
    await waitFor(() => expect(search().get("page")).toBe("3"));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(screen.queryByText(/No datasets/)).toBeNull();
  });

  it("steps back after the last page empties (a delete elsewhere), not to an empty state", async () => {
    byTenant.t1 = many(13);
    const { client } = renderPage("/datasets?page=2");
    await waitFor(() => expect(cards()).toHaveLength(1));
    byTenant.t1 = many(12);
    await act(async () => {
      await client.invalidateQueries();
    });
    await waitFor(() => expect(search().has("page")).toBe(false));
    await waitFor(() => expect(cards()).toHaveLength(12));
    expect(screen.queryByText("No datasets yet")).toBeNull();
  });

  it("treats a malformed page (0, negative, text, fractional) as page 1", async () => {
    for (const bad of ["0", "-3", "abc", "2.5", ""]) {
      calls = [];
      const view = renderPage(`/datasets?page=${bad}`);
      await screen.findByTestId("dataset-grid");
      expect(listCalls()[0]?.params).toMatchObject({ page: 1 });
      view.unmount();
    }
  });

  it("cuts a 300 character keywords value to 128 characters before the request", async () => {
    renderPage(`/datasets?keywords=${"a".repeat(300)}`);
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(0));
    expect(String(listCalls()[0]?.params.keywords)).toHaveLength(128);
    expect(String(listCalls()[0]?.params.keywords)).toBe("a".repeat(128));
  });

  it("searches after the debounce, resets the page to 1 and puts keywords in the URL", async () => {
    renderPage("/datasets?page=2");
    await waitFor(() => expect(search().get("page")).toBe("2"));
    await screen.findByTestId("dataset-grid");
    const field = screen.getByRole("searchbox", { name: "Search datasets" });
    vi.useFakeTimers();
    fireEvent.change(field, { target: { value: "Dataset 2" } });
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(search().has("keywords")).toBe(false);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    vi.useRealTimers();
    expect(search().get("keywords")).toBe("Dataset 2");
    expect(search().has("page")).toBe(false);
    await waitFor(() => expect(listCalls().at(-1)?.params).toMatchObject({ page: 1, keywords: "Dataset 2" }));
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(cards().length).toBeLessThan(12);
  });
});

describe("Workspace scope (D-26, TEN-13)", () => {
  it("lists a joined workspace's datasets and resets page and keywords when the workspace changes", async () => {
    memberships = [OWN, joined("normal")];
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    byTenant.t1 = many(25);
    renderPage("/datasets?page=2&keywords=Dataset");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(listCalls().at(-1)?.params).toMatchObject({ tenant_id: "t1", page: 2, keywords: "Dataset" });
    act(() => useWorkspaceStore.getState().setActive("t9"));
    await waitFor(() => expect(search().has("page")).toBe(false));
    expect(search().has("keywords")).toBe(false);
    await waitFor(() => expect(listCalls().at(-1)?.params).toMatchObject({ tenant_id: "t9", page: 1 }));
    expect(listCalls().at(-1)?.params.keywords).toBeUndefined();
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.getByText("Datasets in Grace's workspace. You see the ones you created and the ones shared with the team.")).toBeInTheDocument();
  });

  it("never shows the first workspace's datasets under the second", async () => {
    memberships = [OWN, joined("normal")];
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    renderPage();
    await waitFor(() => expect(cards()).toHaveLength(3));
    act(() => useWorkspaceStore.getState().setActive("t9"));
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.queryByText("Dataset 03")).toBeNull();
    expect(document.body.innerHTML).not.toContain("ds-t1-");
  });
});

describe("Missing default embedding model notice (D-18)", () => {
  beforeEach(() => {
    defaultsByTenant.t1 = { chat: "", embedding: "" };
  });

  it("shows owners the info notice with the link to model settings", async () => {
    renderPage();
    const notice = await screen.findByTestId("datasets-missing-default");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice).toHaveTextContent("This workspace has no default embedding model yet, so datasets can't be created.");
    expect(notice).not.toHaveTextContent("Ask the owner or an admin to choose one.");
    expect(within(notice).getByRole("link", { name: "Open model settings" })).toHaveAttribute("href", "/user-setting/model");
  });

  it("shows members the sentence asking the owner or an admin and no link", async () => {
    memberships = [OWN, joined("normal")];
    byTenant.t9 = many(2, "t9");
    defaultsByTenant.t9 = { chat: "", embedding: "" };
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    useWorkspaceStore.getState().setActive("t9");
    renderPage();
    const notice = await screen.findByTestId("datasets-missing-default");
    expect(notice).toHaveTextContent("This workspace has no default embedding model yet, so datasets can't be created. Ask the owner or an admin to choose one.");
    expect(within(notice).queryByRole("link")).toBeNull();
  });

  it("is absent when the workspace has a default, and while the defaults are still loading", async () => {
    defaultsByTenant.t1 = { chat: "", embedding: EMBED };
    renderPage();
    await screen.findByTestId("dataset-grid");
    expect(screen.queryByTestId("datasets-missing-default")).toBeNull();
  });

  it("opens the blocked form from Create dataset", async () => {
    renderPage();
    await screen.findByTestId("datasets-missing-default");
    await userEvent.click(await screen.findByTestId("dataset-create"));
    expect(await screen.findByTestId("create-dataset-blocked")).toBeInTheDocument();
  });
});

describe("Create dataset from the gallery", () => {
  it("opens the dialog from the header action and returns focus to it on close", async () => {
    renderPage();
    await screen.findByTestId("dataset-grid");
    const button = screen.getByTestId("dataset-create");
    await userEvent.click(button);
    const dialog = await screen.findByTestId("create-dataset-dialog");
    expect(within(dialog).getByRole("heading", { name: "Create dataset" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("create-dataset-dialog")).toBeNull());
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("opens the dialog from the empty state action", async () => {
    byTenant.t1 = [];
    renderPage();
    await userEvent.click(await screen.findByTestId("dataset-create"));
    expect(await screen.findByTestId("create-dataset-dialog")).toBeInTheDocument();
  });
});

describe("Language", () => {
  it("keeps the English strings available for the document title key", () => {
    expect(i18n.t("datasets.documentTitle")).toBe("Datasets - devRag");
  });
});
