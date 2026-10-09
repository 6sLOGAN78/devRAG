import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { CreateDatasetDialog } from ".";

// Drives the real dialog, hooks, services and HTTP client against an in-memory server shaped like plans 03-13 and 03-14:
// the embedding model list, the workspace defaults and the dataset create route. Every id is obviously fake.
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

const EMBED_A = "embed-one@OpenRouter";
const EMBED_B = "embed-two@OpenAI";
const CHAT_A = "chat-one@OpenRouter";

interface Model {
  id: string;
  name: string;
  provider: string;
  type: "chat" | "embedding";
  dimension: number | null;
  max_tokens: number;
  instance: string;
  used_tokens: number;
}
const model = (id: string, type: "chat" | "embedding"): Model => {
  const [name, provider] = id.split("@") as [string, string];
  return { id, name, provider, type, dimension: type === "embedding" ? 8 : null, max_tokens: 8192, instance: "default", used_tokens: 0 };
};
const ALL = [model(CHAT_A, "chat"), model(EMBED_A, "embedding"), model(EMBED_B, "embedding")];

interface Forced {
  status: number;
  message: string;
  reason?: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let models: Model[] = [];
let saved: { chat: string; embedding: string } = { chat: "", embedding: EMBED_A };
let forced: Record<string, Forced> = {};
let hold: Promise<void> | null = null;
let memberships: Array<Record<string, string>> = [];

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
  if (key === "GET /v1/tenant/list") return ok(config, memberships);
  if (key === "GET /api/v1/models") {
    const type = (config.params as { type?: string } | undefined)?.type;
    return ok(config, type === undefined ? models : models.filter((m) => m.type === type));
  }
  if (key === "GET /api/v1/models/default") return ok(config, saved);
  if (key === "POST /api/v1/datasets") {
    const body = JSON.parse(String(config.data)) as Record<string, string>;
    return ok(config, {
      id: "ds-new-1",
      name: body.name,
      description: body.description ?? "",
      permission: body.permission ?? "me",
      embd_id: body.embd_id ?? "",
      embedding_dimension: 8,
      doc_num: 0,
      created_by: "u1",
      tenant_id: body.tenant_id,
      update_time: 1760000000000,
    });
  }
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (hold && config.url === "/api/v1/datasets") await hold;
  return (await Promise.resolve(serve(config))) as never;
};

const posts = () => calls.filter((c) => c.method?.toUpperCase() === "POST" && c.url === "/api/v1/datasets");
const body = (config: InternalAxiosRequestConfig | undefined) => JSON.parse(String(config?.data)) as Record<string, string>;

function Probe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function Harness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <CreateDatasetDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) onClose?.();
        }}
      />
      <p data-testid="dialog-state">{open ? "open" : "closed"}</p>
    </>
  );
}

function renderDialog(onClose?: () => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/datasets"]}>
        <Harness onClose={onClose} />
        <Probe />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

const nameField = () => screen.getByTestId("field-dataset-name") as HTMLInputElement;
const embeddingField = () => screen.getByTestId("field-dataset-embedding") as HTMLSelectElement;
const submit = () => screen.getByTestId("create-dataset-submit");

async function ready() {
  await screen.findByTestId("field-dataset-name");
  await waitFor(() => expect(embeddingField().value).toBe(saved.embedding));
}

beforeEach(() => {
  calls = [];
  models = [...ALL];
  saved = { chat: "", embedding: EMBED_A };
  forced = {};
  hold = null;
  memberships = [];
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

describe("Create dataset dialog (KB-01, KB-02, D-08)", () => {
  it("opens with the name focused, the workspace default embedding model preselected and 'Only me' chosen", async () => {
    renderDialog();
    const dialog = await screen.findByTestId("create-dataset-dialog");
    expect(within(dialog).getByRole("heading", { name: "Create dataset" })).toBeInTheDocument();
    await ready();
    expect(nameField()).toHaveFocus();
    expect(embeddingField().value).toBe(EMBED_A);
    expect(within(embeddingField()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "embed-one", "embed-two"]);
    const visibility = screen.getByTestId("field-dataset-visibility");
    expect(within(visibility).getByRole("radio", { name: /Only me/ })).toBeChecked();
    expect(within(visibility).getByRole("radio", { name: /Whole team/ })).not.toBeChecked();
    expect(within(visibility).getByText("Everyone in Ada's workspace can see it and upload documents. Only you, the owner and admins can change or delete it.")).toBeInTheDocument();
    expect(screen.getByText("Used to index this dataset's documents. It can't be changed once the dataset has documents.")).toBeInTheDocument();
    expect(screen.queryByTestId("create-dataset-blocked")).toBeNull();
  });

  it("shows skeleton fields while the defaults load and an in-dialog error with Try again when they fail", async () => {
    forced["GET /api/v1/models/default"] = { status: 503, message: "down" };
    renderDialog();
    expect(await screen.findByTestId("create-dataset-skeleton")).toBeInTheDocument();
    const state = await screen.findByTestId("error-state");
    expect(within(state).getByRole("heading", { name: "Couldn't load model settings" })).toBeInTheDocument();
    delete forced["GET /api/v1/models/default"];
    await userEvent.click(within(state).getByRole("button", { name: "Try again" }));
    await ready();
  });

  it("shows the description count from 400 characters and refuses more than 500", async () => {
    renderDialog();
    await ready();
    const field = screen.getByTestId("field-dataset-description") as HTMLTextAreaElement;
    expect(screen.queryByText(/\/500$/)).toBeNull();
    await userEvent.click(field);
    await userEvent.paste("x".repeat(399));
    expect(screen.queryByText(/\/500$/)).toBeNull();
    await userEvent.paste("y");
    expect(screen.getByText("400/500")).toBeInTheDocument();
    await userEvent.paste("z".repeat(150));
    expect(field.value).toHaveLength(500);
    expect(screen.getByText("500/500")).toBeInTheDocument();
  });

  it("posts the trimmed name, the default permission 'me' and the preselected model with the active tenant id", async () => {
    renderDialog();
    await ready();
    await userEvent.type(nameField(), "  Quarterly reports  ");
    await userEvent.click(submit());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(body(posts()[0])).toEqual({ tenant_id: "t1", name: "Quarterly reports", embd_id: EMBED_A, permission: "me" });
    expect(posts()[0]?.timeout).toBe(30000);
  });

  it("sends the description and the chosen model and visibility", async () => {
    renderDialog();
    await ready();
    await userEvent.type(nameField(), "Team notes");
    await userEvent.type(screen.getByTestId("field-dataset-description"), "Shared notes");
    await userEvent.selectOptions(embeddingField(), EMBED_B);
    await userEvent.click(within(screen.getByTestId("field-dataset-visibility")).getByRole("radio", { name: /Whole team/ }));
    await userEvent.click(submit());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(body(posts()[0])).toEqual({ tenant_id: "t1", name: "Team notes", description: "Shared notes", embd_id: EMBED_B, permission: "team" });
  });

  it("validates before sending: an empty or blank name, a name over 128 characters and no embedding model", async () => {
    renderDialog();
    await ready();
    await userEvent.click(submit());
    expect(await screen.findByText("Enter a name.")).toBeInTheDocument();
    await userEvent.type(nameField(), "   ");
    await userEvent.click(submit());
    expect(await screen.findByText("Enter a name.")).toBeInTheDocument();
    await userEvent.clear(nameField());
    await userEvent.click(nameField());
    await userEvent.paste("n".repeat(129));
    await userEvent.click(submit());
    expect(await screen.findByText("Use 128 characters or fewer.")).toBeInTheDocument();
    await userEvent.clear(nameField());
    await userEvent.type(nameField(), "ok");
    await userEvent.selectOptions(embeddingField(), "");
    await userEvent.click(submit());
    expect(await screen.findByText("Choose an embedding model.")).toBeInTheDocument();
    expect(posts()).toHaveLength(0);
  });

  it("on success toasts 'Dataset created', closes and opens the new dataset's page", async () => {
    const onClose = vi.fn();
    renderDialog(onClose);
    await ready();
    await userEvent.type(nameField(), "Reports");
    await userEvent.click(submit());
    expect(await screen.findByText("Dataset created")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/dataset/files?id=ds-new-1"));
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByTestId("dialog-state")).toHaveTextContent("closed");
    expect(screen.queryByTestId("create-dataset-dialog")).toBeNull();
  });

  it("ignores a second submit while the first is in flight and marks the form busy", async () => {
    let release: () => void = () => {};
    hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderDialog();
    await ready();
    await userEvent.type(nameField(), "Once");
    await userEvent.click(submit());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(screen.getByTestId("create-dataset-form")).toHaveAttribute("aria-busy", "true");
    expect(submit()).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(submit());
    await userEvent.type(nameField(), "{Enter}");
    expect(posts()).toHaveLength(1);
    release();
    await waitFor(() => expect(screen.getByTestId("dialog-state")).toHaveTextContent("closed"));
    expect(posts()).toHaveLength(1);
  });
});

describe("Create dataset errors (D-18)", () => {
  async function fill(name = "Reports") {
    renderDialog();
    await ready();
    await userEvent.type(nameField(), name);
    await userEvent.click(submit());
  }

  it("puts a duplicate_name answer under Name, names the dataset and focuses the field", async () => {
    forced["POST /api/v1/datasets"] = { status: 409, message: "a dataset with that name already exists", reason: "duplicate_name" };
    await fill();
    const message = await screen.findByText('A dataset named "Reports" already exists in this workspace. Choose another name.');
    expect(message).toBeInTheDocument();
    expect(screen.getByTestId("create-dataset-dialog")).toContainElement(message);
    await waitFor(() => expect(nameField()).toHaveFocus());
    expect(nameField()).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByTestId("create-dataset-error")).toBeNull();
    expect(screen.getByTestId("dialog-state")).toHaveTextContent("open");
  });

  it("puts a model_unavailable answer under Embedding model and refetches the models", async () => {
    forced["POST /api/v1/datasets"] = { status: 400, message: "that embedding model is not available in this workspace", reason: "model_unavailable" };
    renderDialog();
    await ready();
    const before = calls.filter((c) => c.url === "/api/v1/models").length;
    models = [model(EMBED_B, "embedding")];
    await userEvent.type(nameField(), "Reports");
    await userEvent.click(submit());
    expect(await screen.findByText("That embedding model is no longer available in this workspace. Choose another one.")).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/v1/models").length).toBeGreaterThan(before));
    await waitFor(() => expect(within(embeddingField()).queryByRole("option", { name: "embed-one" })).toBeNull());
    expect(embeddingField().value).toBe("");
    expect(embeddingField()).toHaveAttribute("aria-invalid", "true");
  });

  it("switches to the blocked form when the server reports no_default_embedding", async () => {
    forced["POST /api/v1/datasets"] = { status: 400, message: "choose an embedding model", reason: "no_default_embedding" };
    await fill();
    expect(await screen.findByTestId("create-dataset-blocked")).toBeInTheDocument();
    expect(screen.queryByTestId("field-dataset-name")).toBeNull();
  });

  it("shows an alert for index_unavailable (503) with the fixed sentence, keeping the typed name", async () => {
    forced["POST /api/v1/datasets"] = { status: 503, message: "the search index is not available, try again shortly", reason: "index_unavailable" };
    await fill();
    const alert = await screen.findByTestId("create-dataset-error");
    expect(alert).toHaveTextContent("The search index isn't available right now, so the dataset wasn't created. Try again in a moment.");
    expect(nameField().value).toBe("Reports");
    expect(submit()).not.toHaveAttribute("aria-disabled", "true");
  });

  it("shows the lost-permission alert for 403 and the workspace name", async () => {
    forced["POST /api/v1/datasets"] = { status: 403, message: "forbidden" };
    await fill();
    expect(await screen.findByTestId("create-dataset-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
  });

  it("shows a bounded server message for another refusal and the fallback for anything else", async () => {
    forced["POST /api/v1/datasets"] = { status: 503, message: "another dataset is being created, try again shortly", reason: "busy" };
    await fill();
    expect(await screen.findByTestId("create-dataset-error")).toHaveTextContent("another dataset is being created, try again shortly");
    forced["POST /api/v1/datasets"] = { status: 500, message: "x".repeat(400) };
    await userEvent.click(submit());
    await waitFor(() => expect(screen.getByTestId("create-dataset-error")).toHaveTextContent("The dataset wasn't created. Try again."));
  });

  it("renders a hostile server message as text, never as markup", async () => {
    forced["POST /api/v1/datasets"] = { status: 400, message: "<img src=x onerror=alert(1)>", reason: "dataset_invalid" };
    await fill();
    const alert = await screen.findByTestId("create-dataset-error");
    expect(alert.querySelector("img")).toBeNull();
    expect(alert).toHaveTextContent("<img src=x onerror=alert(1)>");
  });
});

describe("Blocked form when the workspace has no default embedding model (D-18)", () => {
  beforeEach(() => {
    saved = { chat: "", embedding: "" };
  });

  it("explains what is missing and links owners to model settings, with nothing auto-picked", async () => {
    renderDialog();
    const blocked = await screen.findByTestId("create-dataset-blocked");
    expect(within(blocked).getByRole("heading", { name: "Choose a default embedding model first" })).toBeInTheDocument();
    expect(within(blocked).getByText("A dataset needs an embedding model to index its documents, and this workspace has no default yet.")).toBeInTheDocument();
    expect(within(blocked).getByRole("link", { name: "Open model settings" })).toHaveAttribute("href", "/user-setting/model");
    expect(within(blocked).queryByText("Ask the workspace owner or an admin to choose one.")).toBeNull();
    expect(within(blocked).getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.queryByTestId("field-dataset-name")).toBeNull();
    expect(posts()).toHaveLength(0);
  });

  it("treats a default whose model is gone as no default", async () => {
    saved = { chat: "", embedding: "gone-model@OpenRouter" };
    renderDialog();
    expect(await screen.findByTestId("create-dataset-blocked")).toBeInTheDocument();
  });

  it("gives a member the Ask sentence and only Close, with no link", async () => {
    // A joined workspace where the caller is a plain member.
    memberships = [{ tenant_id: "t9", tenant_name: "Grace's workspace", owner_nickname: "Grace", owner_avatar: "", role: "normal", joined_time: "2026-10-01T12:00:00Z" }];
    const rows = [{ tenantId: "t9", tenantName: "Grace's workspace", ownerNickname: "Grace", ownerAvatar: "", role: "normal", joinedTime: "2026-10-01T12:00:00Z" }];
    useWorkspaceStore.getState().initialise("u1", "t1", rows);
    useWorkspaceStore.getState().setActive("t9");
    renderDialog();
    const blocked = await screen.findByTestId("create-dataset-blocked");
    expect(within(blocked).getByText("Ask the workspace owner or an admin to choose one.")).toBeInTheDocument();
    expect(within(blocked).queryByRole("link")).toBeNull();
    expect(within(blocked).getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("closes from the footer Close button", async () => {
    const onClose = vi.fn();
    renderDialog(onClose);
    const blocked = await screen.findByTestId("create-dataset-blocked");
    await userEvent.click(within(blocked).getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
