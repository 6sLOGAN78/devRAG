import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toAssistantDetail } from "@/services/chat-service";
import { waitUntil } from "@/test/wait-until";
import { assistantRow } from "@/test/server-areas/assistants";
import { setAssistants, setMembersWithChats } from "@/test/server-areas/assistants";
import { createDatasetServer, datasetRow, membershipRow, storedMemberships, DATASET_ID, OTHER_DATASET_ID } from "@/test/dataset-server";
import { http, registerQueryClient } from "@/services/http";
import { notifySuccess } from "@/services/notify";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { setAuthorization } from "@/utils/authorization";
import en from "@/locales/areas/en/assistant.json";
import { AvatarPicker, readAvatar } from "./avatar-picker";
import { DatasetChecklist } from "./dataset-checklist";
import { assistantSchema, changesOf, type AssistantFormValues } from "./schemas";
import { AssistantDialog } from ".";

vi.mock("@/services/notify", () => ({ notifySuccess: vi.fn(), notifyError: vi.fn() }));

const values = (): AssistantFormValues => ({ name: "Assistant 1", icon: "", permission: "me", kbIds: [], llmId: "chat-one@OpenRouter", rerankId: "", system: "instructions", prologue: "hello", emptyResponse: "nothing found", similarityThreshold: 0.2, vectorSimilarityWeight: 0.3, topN: 6 });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("assistant schema and changed fields", () => {
  it("accepts valid defaults and trims names", () => expect(assistantSchema.parse({ ...values(), name: "  Name  " }).name).toBe("Name"));
  it.each([
    ["name", " "], ["name", "x".repeat(129)], ["system", "x".repeat(8001)], ["prologue", "x".repeat(501)],
    ["emptyResponse", ""], ["emptyResponse", "x".repeat(501)], ["topN", 0], ["topN", 31], ["topN", 1.5],
    ["similarityThreshold", -0.05], ["similarityThreshold", 0.22], ["vectorSimilarityWeight", 1.05], ["llmId", ""],
  ])("refuses out-of-bounds %s", (field, value) => expect(assistantSchema.safeParse({ ...values(), [field as string]: value }).success).toBe(false));
  it("sends only changed fields including nested prompt changes", () => {
    const detail = toAssistantDetail(assistantRow(1, { prompt_config: { system: "instructions", prologue: "hello", empty_response: "nothing found" } }));
    expect(changesOf(detail, values())).toEqual({});
    expect(changesOf(detail, { ...values(), name: "new", system: "changed" })).toEqual({ name: "new", promptConfig: { system: "changed" } });
  });
  it("compares dataset selections as a set and clears the reranker with null", () => {
    const detail = toAssistantDetail(assistantRow(1, { kb_ids: ["a", "b"], rerank_id: "r", prompt_config: { system: "instructions", prologue: "hello", empty_response: "nothing found" } }));
    expect(changesOf(detail, { ...values(), kbIds: ["b", "a"] })).toEqual({ rerankId: null });
  });
});

describe("assistant picture", () => {
  beforeEach(() => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 240, height: 120, close: vi.fn() }));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as never);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation(function (this: HTMLCanvasElement) { expect(this.width).toBe(128); expect(this.height).toBe(128); return "data:image/png;base64,YQ=="; });
  });
  it("re-encodes an image to the bounded PNG canvas", async () => expect(await readAvatar(new File(["raster"], "image.jpg", { type: "image/jpeg" }))).toBe("data:image/png;base64,YQ=="));
  it("rejects SVG and other non-raster inputs", async () => expect(readAvatar(new File(["<svg/>"], "x.svg", { type: "image/svg+xml" }))).rejects.toThrow("assistant.picture.type"));
  it("rejects files larger than 1 MiB", async () => expect(readAvatar(new File([new Uint8Array(1048577)], "x.png", { type: "image/png" }))).rejects.toThrow("assistant.picture.size"));
  it("shows a decoding error without changing the value", async () => {
    vi.mocked(createImageBitmap).mockRejectedValueOnce(new Error("bad bitmap")); const onChange = vi.fn(); render(<AvatarPicker value="" onChange={onChange} />);
    fireEvent.change(screen.getByTestId("assistant-avatar-input"), { target: { files: [new File(["bad"], "x.png", { type: "image/png" })] } });
    await waitUntil(() => screen.queryByText("The image couldn't be read.")); expect(onChange).not.toHaveBeenCalled();
  });
  it("uses only PNG/JPEG data URLs for previews", () => {
    const { container } = render(<AvatarPicker value="https://evil.invalid/avatar.png" onChange={vi.fn()} />); expect(container.querySelector("img")).toBeNull();
  });
  it("removes a stored image", () => { const onChange = vi.fn(); render(<AvatarPicker value="data:image/png;base64,YQ==" onChange={onChange} />); fireEvent.click(screen.getByRole("button", { name: "Remove image" })); expect(onChange).toHaveBeenCalledWith(""); });
});

describe("assistant dataset checklist", () => {
  const datasets = [{ id: "a", name: "Private handbook", permission: "me" }, { id: "b", name: "Team handbook", permission: "team" }];
  it("disables private rows for a shared assistant with a visible reason", () => {
    render(<MemoryRouter><DatasetChecklist datasets={datasets} selected={[]} permission="team" onToggle={vi.fn()} unavailableCount={0} /></MemoryRouter>);
    expect(screen.getByRole("checkbox", { name: "Private handbook" })).toBeDisabled(); expect(screen.getByText("Only you can see this dataset, so a shared assistant can't use it.")).toBeInTheDocument();
  });
  it("allows a private assistant to select private datasets", () => {
    const toggle = vi.fn(); render(<MemoryRouter><DatasetChecklist datasets={datasets} selected={[]} permission="me" onToggle={toggle} unavailableCount={0} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("checkbox", { name: "Private handbook" })); expect(toggle).toHaveBeenCalledWith("a", true);
  });
  it("explains unavailable bindings with a plural count", () => {
    render(<MemoryRouter><DatasetChecklist datasets={datasets} selected={[]} permission="me" onToggle={vi.fn()} unavailableCount={2} /></MemoryRouter>);
    expect(screen.getByTestId("assistant-datasets-unavailable")).toHaveTextContent("2 datasets used by this assistant aren't available to you. They stay linked.");
  });
  it("links to the datasets page when the list is empty", () => {
    render(<MemoryRouter><DatasetChecklist datasets={[]} selected={[]} permission="me" onToggle={vi.fn()} unavailableCount={0} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Datasets page" })).toHaveAttribute("href", "/datasets");
  });
});

describe("AssistantDialog create and settings", () => {
  const server = createDatasetServer(), A = assistantRow().id, originalAdapter = http.defaults.adapter;
  let client: QueryClient;
  let models: Record<string, unknown>[];
  const owner = { id: "u1", nickname: "Ada", email: "ada@example.test", avatar: "", language: "English", colorSchema: "Bright", tenantId: "t1", tenantName: "Workspace", role: "owner", isSuperuser: false };
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter><QueryClientProvider client={client}>{children}</QueryClientProvider></MemoryRouter>;
  function Harness({ mode = "create", id = A, saved }: { mode?: "create" | "settings"; id?: string; saved: (value: unknown) => void }) {
    const [open, setOpen] = useState(true);
    return <><button data-testid="open-assistant" onClick={() => setOpen(true)}>Open</button><AssistantDialog open={open} onOpenChange={setOpen} mode={mode} assistantId={id} onSaved={saved} /></>;
  }
  const open = (mode: "create" | "settings" = "create", id = A) => {
    const saved = vi.fn(), view = render(<Harness mode={mode} id={id} saved={saved} />, { wrapper });
    return { ...view, saved, select: (next: string) => view.rerender(<Harness mode={mode} id={next} saved={saved} />) };
  };
  const ready = () => waitUntil(() => screen.queryByTestId("field-assistant-name"));
  const name = (value: string) => fireEvent.change(screen.getByTestId("field-assistant-name"), { target: { value } });
  const submit = () => fireEvent.click(screen.getByTestId("assistant-submit"));
  const body = (method: string, path: string) => JSON.parse(String(server.callsTo(method, path).at(-1)?.data)) as Record<string, unknown>;
  const joined = (role: "admin" | "normal") => {
    const rows = [membershipRow("t1", "Workspace", role)];
    server.memberships = rows;
    useUserStore.getState().setUser({ ...owner, tenantId: "own" });
    client.setQueryData(MEMBERSHIPS_QUERY_KEY, storedMemberships(rows));
    useWorkspaceStore.getState().initialise(owner.id, "own", storedMemberships(rows));
    useWorkspaceStore.getState().setActive("t1");
  };
  beforeEach(() => {
    server.reset(); http.defaults.adapter = server.adapter;
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); registerQueryClient(client);
    useUserStore.getState().setUser(owner); useWorkspaceStore.getState().reset(); setAuthorization("test-token");
    client.setQueryData(MEMBERSHIPS_QUERY_KEY, []);
    setAssistants(server, [assistantRow()]);
    server.datasets[DATASET_ID] = datasetRow({ name: "Shared handbook" });
    server.datasets[OTHER_DATASET_ID] = datasetRow({ id: OTHER_DATASET_ID, name: "Private handbook", permission: "me" });
    models = [{ id: "chat-one@OpenRouter", name: "chat-one", provider: "OpenRouter", type: "chat" }, { id: "rank@TEI", name: "rank", provider: "TEI", type: "rerank" }];
    server.use(({ url, method, params, ok }) => {
      if (method === "GET" && url === "/api/v1/models") return ok(models.filter((m) => !params.type || m.type === params.type));
      if (method === "GET" && url === "/api/v1/datasets") {
        const rows = Object.values(server.datasets).filter((r) => r.permission === "team" || r.created_by === server.uploader);
        const page = Number(params.page ?? 1), size = Number(params.page_size ?? 100);
        return ok({ items: rows.slice((page - 1) * size, page * size), total: rows.length });
      }
      return undefined;
    });
    vi.mocked(notifySuccess).mockClear();
  });
  afterEach(() => { cleanup(); client.clear(); http.defaults.adapter = originalAdapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); });

  it("focuses Name and prefills all documented create defaults", async () => {
    open(); await ready(); expect(screen.getByTestId("field-assistant-name")).toHaveFocus();
    expect(screen.getByTestId("field-assistant-system")).toHaveValue(en.assistant.default.system);
    expect(screen.getByTestId("field-assistant-threshold")).toHaveValue("0.2"); expect(screen.getByTestId("field-assistant-weight")).toHaveValue("0.3");
    expect(screen.getByTestId("field-assistant-topn")).toHaveValue(6); expect(screen.getByTestId("assistant-visibility-me")).toBeChecked();
    expect(screen.getByTestId("field-assistant-rerank")).toHaveValue(""); expect(screen.getByTestId("assistant-submit")).toHaveAttribute("aria-disabled", "true");
  });
  it("creates from the chosen visible datasets and reports the new id", async () => {
    const view = open(); await ready(); name("New assistant"); fireEvent.click(screen.getByRole("checkbox", { name: "Shared handbook" })); submit();
    await waitUntil(() => view.saved.mock.calls.length === 1);
    expect(body("POST", "/api/v1/chats")).toMatchObject({ name: "New assistant", tenant_id: "t1", kb_ids: [DATASET_ID], llm_id: "chat-one@OpenRouter", top_n: 6 });
    expect(view.saved).toHaveBeenCalledWith(expect.objectContaining({ created: true })); expect(notifySuccess).toHaveBeenCalledWith("Assistant created");
  });
  it("saves only a changed setting", async () => {
    const view = open("settings"); await ready(); expect(screen.getByTestId("assistant-submit")).toHaveAttribute("aria-disabled", "true"); name("Renamed"); submit();
    await waitUntil(() => view.saved.mock.calls.length === 1); expect(body("PUT", `/api/v1/chats/${A}`)).toEqual({ name: "Renamed" });
    expect(view.saved).toHaveBeenCalledWith({ id: A, created: false }); expect(notifySuccess).toHaveBeenCalledWith("Assistant saved");
  });
  it("disables Whole team when a private dataset is checked", async () => {
    open(); await ready(); fireEvent.click(screen.getByRole("checkbox", { name: "Private handbook" }));
    expect(screen.getByTestId("assistant-visibility-team")).toBeDisabled(); expect(screen.getByTestId("assistant-share-reason")).toBeVisible();
  });
  it("disables private dataset rows after Whole team is chosen", async () => {
    open(); await ready(); fireEvent.click(screen.getByTestId("assistant-visibility-team")); expect(screen.getByRole("checkbox", { name: "Private handbook" })).toBeDisabled();
  });
  it.each([1, 2])("shows the narrowing refusal for %i teammates without stacking a confirmation", async (count) => {
    setAssistants(server, [assistantRow(1, { permission: "team" })]); setMembersWithChats(server, A, count); open("settings"); await ready();
    expect(screen.getByTestId("assistant-narrowing-info")).toBeInTheDocument(); fireEvent.click(screen.getByTestId("assistant-visibility-me")); submit();
    await waitUntil(() => screen.queryByTestId("assistant-error")); expect(screen.getByTestId("assistant-error")).toHaveTextContent(`${count} ${count === 1 ? "teammate has" : "teammates have"}`);
    expect(screen.getByTestId("assistant-visibility-me")).toBeChecked(); expect(screen.queryByRole("alertdialog")).toBeNull();
  });
  it("keeps hidden bindings and sends only checked visible ids", async () => {
    server.datasets[OTHER_DATASET_ID]!.created_by = "other";
    const extra = "3".repeat(32); server.datasets[extra] = datasetRow({ id: extra, name: "Another shared handbook" });
    setAssistants(server, [assistantRow(1, { kb_ids: [DATASET_ID, OTHER_DATASET_ID] })]); const view = open("settings"); await ready();
    expect(screen.getByTestId("assistant-datasets-unavailable")).toHaveTextContent("1 dataset"); expect(screen.queryByRole("checkbox", { name: "Private handbook" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "Another shared handbook" })); submit(); await waitUntil(() => view.saved.mock.calls.length === 1);
    expect(body("PUT", `/api/v1/chats/${A}`).kb_ids).toEqual([DATASET_ID, extra]);
  });
  it("places a duplicate-name refusal under Name and focuses it", async () => {
    server.forced["POST /api/v1/chats"] = { status: 409, reason: "duplicate_name", message: "duplicate" }; open(); await ready(); name("Duplicate"); submit();
    await waitUntil(() => screen.queryByText(/An assistant named/)); expect(screen.getByTestId("field-assistant-name")).toHaveFocus(); expect(screen.queryByTestId("assistant-error")).toBeNull();
  });
  it.each([
    [403, "forbidden", "workspace.forbidden"], [404, "not_found", "assistant.error.gone"], [502, "provider_unreachable", "assistant.error.fallback"],
  ])("places a %i refusal in the form alert", async (status, reason) => {
    server.forced["POST /api/v1/chats"] = { status: status as number, reason: reason as string, message: "server text" }; open(); await ready(); name("New"); submit();
    await waitUntil(() => screen.queryByTestId("assistant-error")); expect(screen.getByTestId("assistant-error")).not.toHaveTextContent("server text");
  });
  it("flags the server's unshared dataset ids", async () => {
    server.forced["POST /api/v1/chats"] = { status: 409, reason: "assistant_dataset_not_shared", message: "not shared", data: { dataset_ids: [DATASET_ID] } };
    open(); await ready(); name("New"); submit(); await waitUntil(() => screen.queryByTestId("assistant-error"));
    expect(screen.getAllByTestId("assistant-dataset-option").find((r) => r.dataset.datasetId === DATASET_ID)).toHaveAttribute("data-invalid", "true");
  });
  it("refetches datasets after a dataset-not-found refusal", async () => {
    server.forced["POST /api/v1/chats"] = { status: 404, reason: "dataset_not_found", message: "gone" }; open(); await ready(); const before = server.callsTo("GET", "/api/v1/datasets").length;
    name("New"); submit(); await waitUntil(() => screen.queryByText("A dataset you chose is no longer available. Choose again."));
    await waitUntil(() => server.callsTo("GET", "/api/v1/datasets").length > before);
  });
  it.each([400, 409])("refetches models after a %i model-unavailable refusal", async (status) => {
    server.forced["POST /api/v1/chats"] = { status, reason: "model_unavailable", message: "gone" }; open(); await ready(); const before = server.callsTo("GET", "/api/v1/models").length;
    name("New"); submit(); await waitUntil(() => screen.queryByText("That model is no longer available in this workspace. Choose another one.")); await waitUntil(() => server.callsTo("GET", "/api/v1/models").length > before);
  });
  it("ignores a repeated submit and Escape while the save is pending", async () => {
    let release = () => {}; server.holds["POST /api/v1/chats"] = new Promise<void>((r) => { release = r; }); const view = open(); await ready(); name("New");
    fireEvent.submit(screen.getByTestId("assistant-form")); fireEvent.submit(screen.getByTestId("assistant-form")); await waitUntil(() => server.callsTo("POST", "/api/v1/chats").length === 1);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", code: "Escape" }); expect(screen.getByRole("dialog")).toBeInTheDocument();
    await act(async () => release()); await waitUntil(() => view.saved.mock.calls.length === 1); expect(server.callsTo("POST", "/api/v1/chats")).toHaveLength(1);
  });
  it("discards edits on close and does not carry an error from A to B", async () => {
    const B = assistantRow(2).id; setAssistants(server, [assistantRow(), assistantRow(2)]); server.forced[`PUT /api/v1/chats/${A}`] = { status: 500, message: "failure" };
    const view = open("settings"); await ready(); name("Changed"); submit(); await waitUntil(() => screen.queryByTestId("assistant-error"));
    fireEvent.click(screen.getByTestId("assistant-close")); view.select(B); fireEvent.click(screen.getByTestId("open-assistant")); await ready();
    expect(screen.getByTestId("field-assistant-name")).toHaveValue("Assistant 2"); expect(screen.queryByTestId("assistant-error")).toBeNull();
  });
  it.each(["owner", "admin", "normal"] as const)("shows the no-model form for %s with the appropriate action", async (role) => {
    models = []; if (role !== "owner") joined(role);
    open(); await waitUntil(() => screen.queryByTestId("assistant-blocked"));
    const link = screen.queryByRole("link", { name: "Open model settings" });
    if (role === "normal") {
      expect(link).toBeNull(); expect(screen.getByText(en.assistant.dialog.blocked.bodyMember)).toBeInTheDocument();
      expect(within(screen.getByTestId("assistant-blocked")).getByRole("button", { name: /^Close$/ })).toHaveFocus();
    } else { expect(link).toHaveAttribute("href", "/user-setting/model"); expect(link).toHaveFocus(); }
  });
  it("shows loading fields until models are available", async () => {
    let release = () => {}; server.holds["GET /api/v1/models"] = new Promise<void>((resolve) => { release = resolve; });
    open(); expect(screen.getByTestId("assistant-skeleton")).toBeInTheDocument();
    await act(async () => release()); await ready();
  });
  it("retries a model-list failure in the dialog", async () => {
    server.forced["GET /api/v1/models"] = { status: 502, message: "failure" }; open();
    await waitUntil(() => screen.queryByText("Couldn't load models")); expect(screen.queryByTestId("assistant-form")).toBeNull();
    delete server.forced["GET /api/v1/models"]; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await ready();
  });
  it.each(["owner", "admin"] as const)("reports a non-creator %s narrowing as leaving the list", async (role) => {
    if (role === "admin") joined(role);
    setAssistants(server, [assistantRow(1, { created_by: "other", permission: "team" })]);
    const view = open("settings"); await ready();
    expect(screen.getByTestId("assistant-narrowing-info")).toHaveTextContent(en.assistant.visibility.narrowingCreator);
    fireEvent.click(screen.getByTestId("assistant-visibility-me")); submit();
    await waitUntil(() => view.saved.mock.calls.length === 1);
    expect(view.saved).toHaveBeenCalledWith({ id: A, leftList: true }); expect(notifySuccess).toHaveBeenCalledWith(en.assistant.saved.narrowed);
  });
  it("prevents another member from editing a shared assistant", async () => {
    joined("normal"); setAssistants(server, [assistantRow(1, { created_by: "other", permission: "team" })]); open("settings");
    await waitUntil(() => screen.queryByRole("alert")); expect(screen.queryByTestId("assistant-form")).toBeNull();
  });
  it("saves the re-encoded avatar from the complete form", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 128, height: 256, close: vi.fn() }));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as never);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,YQ==");
    const view = open(); await ready(); name("Image assistant");
    fireEvent.change(screen.getByTestId("assistant-avatar-input"), { target: { files: [new File(["raster"], "x.jpg", { type: "image/jpeg" })] } });
    await waitUntil(() => screen.getByTestId("assistant-avatar-preview").querySelector("img"));
    submit(); await waitUntil(() => view.saved.mock.calls.length === 1); expect(body("POST", "/api/v1/chats").icon).toBe("data:image/png;base64,YQ==");
  });
  it("loads every dataset page before allowing a binding edit", async () => {
    for (let n = 1; n <= 101; n += 1) {
      const id = (n + 500).toString(16).padStart(32, "0"); server.datasets[id] = datasetRow({ id, name: `Option ${n}` });
    }
    open(); await ready(); expect(screen.getByRole("checkbox", { name: "Option 101" })).toBeInTheDocument();
    expect(server.callsTo("GET", "/api/v1/datasets")).toHaveLength(2);
  });
  it("allows Close during a save and isolates the next opening from its completion", async () => {
    let release = () => {}; server.holds["POST /api/v1/chats"] = new Promise<void>((resolve) => { release = resolve; });
    const view = open(); await ready(); name("Old pending"); submit(); await waitUntil(() => server.callsTo("POST", "/api/v1/chats").length === 1);
    fireEvent.click(screen.getByTestId("assistant-close")); expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByTestId("open-assistant")); await ready(); name("Fresh draft");
    await act(async () => release()); await waitUntil(() => server.callsTo("POST", "/api/v1/chats").length === 1 && !client.isMutating());
    expect(screen.getByTestId("field-assistant-name")).toHaveValue("Fresh draft"); expect(view.saved).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", code: "Escape" }); expect(screen.queryByRole("dialog")).toBeNull();
  });
});
