import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { DefaultsCard } from "./defaults-card";

// Drives the real card, hooks, services and HTTP client against an in-memory server shaped like plan 03-13:
// the model list (filtered by `type`) and the defaults route (GET and PATCH). Every id is obviously fake.
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

const CHAT_A = "chat-one@OpenRouter";
const CHAT_B = "chat-two@OpenAI";
const EMBED_A = "embed-one@OpenRouter";
const EMBED_B = "embed-two@OpenAI";

interface Model {
  id: string;
  name: string;
  provider: string;
  type: "chat" | "embedding" | "vision" | "asr";
  dimension: number | null;
  max_tokens: number;
  instance: string;
  used_tokens: number;
}
const model = (id: string, type: "chat" | "embedding" | "vision" | "asr"): Model => {
  const [name, provider] = id.split("@") as [string, string];
  return { id, name, provider, type, dimension: type === "embedding" ? 8 : null, max_tokens: 8192, instance: "default", used_tokens: 0 };
};
const ALL = [model(CHAT_A, "chat"), model(CHAT_B, "chat"), model(EMBED_A, "embedding"), model(EMBED_B, "embedding")];

interface Forced {
  status: number;
  message: string;
  reason?: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let models: Model[] = [];
let saved: { chat: string; embedding: string; vision?:string;asr?:string } = { chat: "", embedding: "" };
let forced: Record<string, Forced> = {};

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const data = f.reason === undefined ? null : { reason: f.reason };
  const response = { data: { code: f.status, message: f.message, data }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

function serve(config: InternalAxiosRequestConfig): unknown {
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  const stop = forced[key];
  if (stop) return failure(config, stop);
  if (key === "GET /api/v1/models") {
    const type = (config.params as { type?: string } | undefined)?.type;
    return ok(config, type === undefined ? models : models.filter((m) => m.type === type));
  }
  if (key === "GET /api/v1/models/default") return ok(config, saved);
  if (key === "PATCH /api/v1/models/default") {
    const body = JSON.parse(String(config.data)) as { chat?: string | null; embedding?: string | null;vision?:string|null;asr?:string|null };
    saved = { ...(body.asr !== undefined ? {asr:body.asr ?? ""} : saved.asr !== undefined ? {asr:saved.asr} : {}), chat: body.chat === undefined ? saved.chat : (body.chat ?? ""), embedding: body.embedding === undefined ? saved.embedding : (body.embedding ?? ""), ...(body.vision !== undefined ? {vision:body.vision ?? ""} : saved.vision !== undefined ? {vision:saved.vision} : {}) };
    return ok(config, saved);
  }
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  return (await Promise.resolve(serve(config))) as never;
};

const patches = () => calls.filter((c) => c.method?.toUpperCase() === "PATCH");

function renderCard(role: string = "owner") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <DefaultsCard role={role} />
      <Toaster />
    </QueryClientProvider>,
  );
}

const chatSelect = () => screen.getByTestId("default-chat") as HTMLSelectElement;
const embeddingSelect = () => screen.getByTestId("default-embedding") as HTMLSelectElement;

beforeEach(() => {
  calls = [];
  models = [...ALL];
  saved = { chat: "", embedding: "" };
  forced = {};
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  useWorkspaceStore.getState().initialise("u1", "t1", []);
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Default models card, owner and admin form (D-18, TEN-12)", () => {
  it("starts both selects on 'Not set' with nothing preselected even though models exist", async () => {
    renderCard();
    await screen.findByTestId("defaults-form");
    expect(screen.getByRole("heading", { name: "Default models" })).toBeInTheDocument();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    expect(chatSelect().value).toBe("");
    expect(embeddingSelect().value).toBe("");
    expect(within(chatSelect()).getByRole("option", { name: "Not set" })).toBeInTheDocument();
    expect(screen.getByLabelText("Default chat model")).toBe(chatSelect());
    expect(screen.getByLabelText("Default embedding model")).toBe(embeddingSelect());
    expect(screen.getByText("New datasets start with this model. Existing datasets keep the model they were created with.")).toBeInTheDocument();
  });

  it("groups the options by provider and filters them by type", async () => {
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    const chatGroups = Array.from(chatSelect().querySelectorAll("optgroup")).map((g) => g.label);
    expect(chatGroups).toEqual(["OpenRouter", "OpenAI"]);
    expect(Array.from(chatSelect().options).map((o) => o.value)).toEqual(["", CHAT_A, CHAT_B]);
    expect(Array.from(embeddingSelect().options).map((o) => o.value)).toEqual(["", EMBED_A, EMBED_B]);
  });

  it("shows the saved defaults selected", async () => {
    saved = { chat: CHAT_B, embedding: EMBED_A };
    renderCard();
    await waitFor(() => expect(chatSelect().value).toBe(CHAT_B));
    expect(embeddingSelect().value).toBe(EMBED_A);
  });

  it("shows 'Not set' for a saved default whose model no longer exists", async () => {
    saved = { chat: "gone@OpenRouter", embedding: EMBED_A };
    renderCard();
    await waitFor(() => expect(embeddingSelect().value).toBe(EMBED_A));
    expect(chatSelect().value).toBe("");
  });

  it("keeps 'Save defaults' aria-disabled until a choice changes, and sends nothing when clicked early", async () => {
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    const submit = screen.getByTestId("defaults-submit");
    expect(submit).toHaveTextContent("Save defaults");
    expect(submit).toHaveAttribute("aria-disabled", "true");
    await user.click(submit);
    expect(patches()).toHaveLength(0);
    await user.selectOptions(chatSelect(), CHAT_A);
    expect(submit).not.toHaveAttribute("aria-disabled", "true");
    await user.selectOptions(chatSelect(), "");
    expect(submit).toHaveAttribute("aria-disabled", "true");
  });

  it("is the only primary button on the card", async () => {
    renderCard();
    await screen.findByTestId("defaults-form");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("sends the tenant and only the changed field as a composite id, then toasts and clears the dirty state", async () => {
    saved = { chat: "", embedding: EMBED_A };
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(embeddingSelect().value).toBe(EMBED_A));
    await user.selectOptions(chatSelect(), CHAT_B);
    await user.click(screen.getByTestId("defaults-submit"));
    await waitFor(() => expect(patches()).toHaveLength(1));
    const call = patches()[0]!;
    expect(call.url).toBe("/api/v1/models/default");
    expect(JSON.parse(String(call.data))).toEqual({ tenant_id: "t1", chat: CHAT_B });
    expect(await screen.findByText("Default models saved")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("defaults-submit")).toHaveAttribute("aria-disabled", "true"));
    expect(chatSelect().value).toBe(CHAT_B);
    expect(embeddingSelect().value).toBe(EMBED_A);
  });

  it("sends null to clear a default back to 'Not set'", async () => {
    saved = { chat: CHAT_A, embedding: EMBED_A };
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(embeddingSelect().value).toBe(EMBED_A));
    await user.selectOptions(embeddingSelect(), "");
    await user.click(screen.getByTestId("defaults-submit"));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(JSON.parse(String(patches()[0]!.data))).toEqual({ tenant_id: "t1", embedding: null });
    await waitFor(() => expect(embeddingSelect().value).toBe(""));
  });

  it("sends both fields when both changed", async () => {
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    await user.selectOptions(chatSelect(), CHAT_A);
    await user.selectOptions(embeddingSelect(), EMBED_B);
    await user.click(screen.getByTestId("defaults-submit"));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(JSON.parse(String(patches()[0]!.data))).toEqual({ tenant_id: "t1", chat: CHAT_A, embedding: EMBED_B });
  });

  it("shows the server message in an inline alert on a refusal and keeps the choice and the form", async () => {
    forced["PATCH /api/v1/models/default"] = { status: 400, message: "that model is not available in this workspace", reason: "model_unavailable" };
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    await user.selectOptions(chatSelect(), CHAT_A);
    await user.click(screen.getByTestId("defaults-submit"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("that model is not available in this workspace");
    expect(chatSelect().value).toBe(CHAT_A);
    expect(screen.queryByText("Default models saved")).toBeNull();
    // Choosing again clears the old message.
    await user.selectOptions(chatSelect(), CHAT_B);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("uses fixed copy, not server text, for a server failure", async () => {
    forced["PATCH /api/v1/models/default"] = { status: 500, message: "stack trace here" };
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    await user.selectOptions(chatSelect(), CHAT_A);
    await user.click(screen.getByTestId("defaults-submit"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The default models weren't saved. Try again.");
    expect(alert).not.toHaveTextContent("stack trace here");
  });

  it("sends one request even when the button is pressed twice quickly", async () => {
    const user = userEvent.setup();
    renderCard();
    await waitFor(() => expect(within(chatSelect()).getAllByRole("option")).toHaveLength(3));
    await user.selectOptions(chatSelect(), CHAT_A);
    const submit = screen.getByTestId("defaults-submit");
    await user.dblClick(submit);
    await waitFor(() => expect(patches().length).toBeGreaterThan(0));
    expect(patches()).toHaveLength(1);
  });
});

describe("Default models card, missing models", () => {
  it("disables the chat select with its helper when there is no chat model", async () => {
    models = models.filter((m) => m.type === "embedding");
    renderCard();
    await waitFor(() => expect(chatSelect()).toBeDisabled());
    expect(screen.getByText("Add a provider with a chat model first.")).toBeInTheDocument();
    expect(embeddingSelect()).not.toBeDisabled();
    expect(screen.queryByText("Add a provider with an embedding model first.")).toBeNull();
  });

  it("disables the embedding select with its helper when there is no embedding model", async () => {
    models = models.filter((m) => m.type === "chat");
    renderCard();
    await waitFor(() => expect(embeddingSelect()).toBeDisabled());
    expect(screen.getByText("Add a provider with an embedding model first.")).toBeInTheDocument();
    expect(chatSelect()).not.toBeDisabled();
  });

  it("disables both selects on an empty workspace and keeps the button disabled", async () => {
    models = [];
    renderCard();
    await waitFor(() => expect(chatSelect()).toBeDisabled());
    expect(embeddingSelect()).toBeDisabled();
    expect(screen.getByTestId("defaults-submit")).toHaveAttribute("aria-disabled", "true");
  });
});

describe("Default models card, member view (D-07)", () => {
  it("shows a read-only definition list with mono ids or 'Not set' and no select or button", async () => {
    saved = { chat: "", embedding: EMBED_A };
    renderCard("normal");
    const embeddingTerm = await screen.findByText("Default embedding model");
    expect(embeddingTerm.tagName).toBe("DT");
    const value = embeddingTerm.nextElementSibling as HTMLElement;
    expect(value.tagName).toBe("DD");
    expect(value).toHaveTextContent(EMBED_A);
    expect(value.className).toContain("font-mono");
    const chatValue = screen.getByText("Default chat model").nextElementSibling as HTMLElement;
    expect(chatValue).toHaveTextContent("Not set");
    expect(chatValue.className).toContain("text-muted-foreground");
    expect(screen.queryByTestId("defaults-form")).toBeNull();
    expect(screen.queryByTestId("defaults-submit")).toBeNull();
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("does not need the model list to render, so a member never triggers it", async () => {
    renderCard("normal");
    await screen.findByText("Default chat model");
    expect(calls.filter((c) => c.url === "/api/v1/models")).toHaveLength(0);
  });
});

describe("Default models card, states", () => {
  it("shows two skeleton fields with an announced status while loading", async () => {
    renderCard();
    expect(screen.getByTestId("defaults-skeleton")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading default models");
    await screen.findByTestId("defaults-form");
    expect(screen.queryByTestId("defaults-skeleton")).toBeNull();
  });

  it("fails in place with the noun 'default models' and recovers with Try again", async () => {
    forced["GET /api/v1/models/default"] = { status: 500, message: "boom" };
    renderCard();
    const state = await screen.findByTestId("error-state");
    expect(within(state).getByRole("heading", { name: "Couldn't load default models" })).toBeInTheDocument();
    delete forced["GET /api/v1/models/default"];
    await userEvent.setup().click(within(state).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("defaults-form")).toBeInTheDocument();
    expect(screen.queryByTestId("error-state")).toBeNull();
  });

  it("asks for the active workspace on every request", async () => {
    renderCard();
    await screen.findByTestId("defaults-form");
    const reads = calls.filter((c) => c.method?.toUpperCase() === "GET" && String(c.url).startsWith("/api/v1/models"));
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.every((c) => (c.params as { tenant_id?: string }).tenant_id === "t1")).toBe(true);
  });
});


it("saves a configured vision default without changing chat or embedding", async () => {
  const vision="picture-model@OpenRouter";
  models=[...ALL,model(vision,"vision")];
  saved={chat:CHAT_A,embedding:EMBED_A,vision:""};
  const user=userEvent.setup();renderCard();
  await screen.findByTestId("default-vision");
  expect(screen.getByLabelText("Default vision model")).toBe(screen.getByTestId("default-vision"));
  await user.selectOptions(screen.getByTestId("default-vision"),vision);
  await user.click(screen.getByTestId("defaults-submit"));
  await waitFor(()=>expect(patches()).toHaveLength(1));
  expect(JSON.parse(String(patches()[0]!.data))).toEqual({tenant_id:"t1",vision});
});

it("saves the configured local speech default without changing existing slots", async () => {
  const asr="faster-whisper-tiny@DeepDoc";
  models=[...ALL,model(asr,"asr")];saved={chat:CHAT_A,embedding:EMBED_A,asr:""};
  const user=userEvent.setup();renderCard();
  const select=await screen.findByLabelText("Default speech model");
  await user.selectOptions(select,asr);await user.click(screen.getByTestId("defaults-submit"));
  await waitFor(()=>expect(patches()).toHaveLength(1));
  expect(JSON.parse(String(patches()[0]!.data))).toEqual({tenant_id:"t1",asr});
  await waitFor(()=>expect(saved.asr).toBe(asr));
});
