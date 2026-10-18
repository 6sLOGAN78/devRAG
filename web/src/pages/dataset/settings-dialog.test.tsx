import { GENERAL_METHOD } from "@/constants/chunk-methods";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DatasetSettingsDialog } from "@/components/dataset-settings-dialog";
import { Toaster } from "@/components/ui/sonner";
import { datasetQueryKey, datasetsQueryKey } from "@/hooks/use-knowledge-request";
import type { SessionUser } from "@/interfaces/user";
import type { DatasetDetailView, DatasetView } from "@/services/dataset-service";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";

// Drives the real settings dialog, hooks, services and HTTP client against an in-memory server shaped like plans
// 03-14 and 03-18: the embedding model list and the PUT route with its refusals.
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

const baseDataset: DatasetView = {
  id: "ds-1",
  name: "Reports",
  description: "Quarterly reports",
  permission: "team",
  embdId: EMBED_A,
  embeddingDimension: 8,
  docNum: 0,
  createdBy: "u1",
  tenantId: "t1",
  updateTime: 1760000000000,
};

interface Forced {
  status: number;
  message: string;
  reason?: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let forced: Record<string, Forced> = {};
let models = [EMBED_A, EMBED_B];

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
  if (key === "GET /v1/tenant/list") return ok(config, []);
  if (key === "GET /api/v1/models") {
    return ok(
      config,
      models.map((id) => {
        const [name, provider] = id.split("@") as [string, string];
        return { id, name, provider, type: "embedding", dimension: 8, max_tokens: 8192, instance: "default", used_tokens: 0 };
      }),
    );
  }
  if (key === "PUT /api/v1/datasets/ds-1") {
    const sent = JSON.parse(String(config.data)) as Record<string, unknown>;
    return ok(config, {
      id: "ds-1",
      name: sent.name ?? baseDataset.name,
      description: sent.description ?? baseDataset.description,
      permission: sent.permission ?? baseDataset.permission,
      embd_id: sent.embd_id ?? baseDataset.embdId,
      embedding_dimension: 8,
      doc_num: 0,
      created_by: "u1",
      tenant_id: "t1",
      update_time: 1760000099000,
    });
  }
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  return (await Promise.resolve(serve(config))) as never;
};

const puts = () => calls.filter((c) => c.method?.toUpperCase() === "PUT" && c.url === "/api/v1/datasets/ds-1");
const sentBody = () => JSON.parse(String(puts()[0]?.data)) as Record<string, unknown>;

function Harness({ dataset }: { dataset: DatasetView | DatasetDetailView }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <DatasetSettingsDialog dataset={dataset} open={open} onOpenChange={setOpen} />
      <p data-testid="dialog-state">{open ? "open" : "closed"}</p>
    </>
  );
}

function renderDialog(dataset: DatasetView | DatasetDetailView = baseDataset) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
  client.setQueryData(datasetQueryKey("t1", "ds-1"), { ...baseDataset, chunkNum: 0 });
  const view = render(
    <QueryClientProvider client={client}>
      <Harness dataset={dataset} />
      <Toaster />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const nameField = () => screen.getByTestId("field-dataset-name") as HTMLInputElement;
const descriptionField = () => screen.getByTestId("field-dataset-description") as HTMLTextAreaElement;
const embeddingField = () => screen.getByTestId("field-dataset-embedding") as HTMLSelectElement;
const submit = () => screen.getByTestId("dataset-settings-submit");
const visibility = () => screen.getByTestId("field-dataset-visibility");
const dialogState = () => screen.getByTestId("dialog-state");

async function ready() {
  await screen.findByTestId("dataset-settings-form");
}

async function readyWithSelect() {
  await ready();
  await waitFor(() => expect(embeddingField().value).toBe(EMBED_A));
}

beforeEach(() => {
  calls = [];
  forced = {};
  models = [EMBED_A, EMBED_B];
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

describe("Dataset settings dialog: the form (KB-06)", () => {
  it("opens titled 'Dataset settings' with every field prefilled and Save settings aria-disabled until something changes", async () => {
    renderDialog();
    const dialog = await screen.findByTestId("dataset-settings-dialog");
    expect(within(dialog).getByRole("heading", { name: "Dataset settings" })).toBeInTheDocument();
    await readyWithSelect();
    expect(nameField().value).toBe("Reports");
    expect(descriptionField().value).toBe("Quarterly reports");
    expect(within(visibility()).getByRole("radio", { name: /Whole team/ })).toBeChecked();
    expect(within(embeddingField()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "embed-one", "embed-two"]);
    expect(submit()).toHaveAttribute("aria-disabled", "true");
    expect(submit()).toHaveTextContent("Save settings");
    await userEvent.click(submit());
    expect(puts()).toHaveLength(0);
    await userEvent.type(nameField(), "2");
    expect(submit()).not.toHaveAttribute("aria-disabled");
  });

  it("returns Save settings to disabled when the edit is undone", async () => {
    renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "2");
    expect(submit()).not.toHaveAttribute("aria-disabled");
    await userEvent.type(nameField(), "{Backspace}");
    expect(submit()).toHaveAttribute("aria-disabled", "true");
  });

  it("shows the embedding model as a select while the dataset has no documents", async () => {
    renderDialog();
    await readyWithSelect();
    expect(embeddingField().tagName).toBe("SELECT");
    expect(screen.queryByTestId("dataset-settings-embedding-fixed")).toBeNull();
  });

  it("shows a read-only field with the helper, and no select, once the dataset has documents", async () => {
    renderDialog({ ...baseDataset, docNum: 2 });
    await ready();
    const fixed = screen.getByTestId("dataset-settings-embedding-fixed");
    expect(fixed).toHaveTextContent("embed-one");
    expect(screen.getByText("The embedding model is fixed once a dataset has documents.")).toBeInTheDocument();
    expect(screen.queryByTestId("field-dataset-embedding")).toBeNull();
    expect(calls.some((c) => c.url === "/api/v1/models")).toBe(false);
  });

  it("also locks the embedding model when the dataset has chunks but no documents are counted", async () => {
    renderDialog({ ...baseDataset, docNum: 0, language: "English", parserId: GENERAL_METHOD, chunkNum: 4, tokenNum: 10, createTime: 1, uploadLimits: null });
    await ready();
    expect(screen.getByTestId("dataset-settings-embedding-fixed")).toBeInTheDocument();
    expect(screen.queryByTestId("field-dataset-embedding")).toBeNull();
  });

  it("shows a skeleton while the models load and an in-dialog error with Try again when they fail", async () => {
    forced["GET /api/v1/models"] = { status: 503, message: "down" };
    renderDialog();
    expect(await screen.findByTestId("dataset-settings-skeleton")).toBeInTheDocument();
    const state = await screen.findByTestId("error-state");
    delete forced["GET /api/v1/models"];
    await userEvent.click(within(state).getByRole("button", { name: "Try again" }));
    await readyWithSelect();
  });

  it("shows the live description counter from 400 characters", async () => {
    renderDialog({ ...baseDataset, description: "x".repeat(399) });
    await readyWithSelect();
    expect(screen.queryByText(/\/500$/)).toBeNull();
    await userEvent.type(descriptionField(), "y");
    expect(screen.getByText("400/500")).toBeInTheDocument();
  });

  it("validates a blank name inline without sending anything", async () => {
    renderDialog();
    await readyWithSelect();
    await userEvent.clear(nameField());
    await userEvent.click(submit());
    expect(await screen.findByText("Enter a name.")).toBeInTheDocument();
    expect(puts()).toHaveLength(0);
  });
});

describe("Dataset settings dialog: narrowing visibility (D-09)", () => {
  it("shows the inline note when Whole team becomes Only me, and hides it again when reverted", async () => {
    renderDialog();
    await readyWithSelect();
    expect(screen.queryByTestId("dataset-settings-narrowing")).toBeNull();
    await userEvent.click(within(visibility()).getByRole("radio", { name: /Only me/ }));
    expect(screen.getByTestId("dataset-settings-narrowing")).toHaveTextContent("Teammates will lose access to this dataset. Documents they uploaded stay in it.");
    await userEvent.click(within(visibility()).getByRole("radio", { name: /Whole team/ }));
    expect(screen.queryByTestId("dataset-settings-narrowing")).toBeNull();
  });

  it("shows no note when Only me becomes Whole team", async () => {
    renderDialog({ ...baseDataset, permission: "me" });
    await readyWithSelect();
    await userEvent.click(within(visibility()).getByRole("radio", { name: /Whole team/ }));
    expect(screen.queryByTestId("dataset-settings-narrowing")).toBeNull();
  });
});

describe("Dataset settings dialog: saving (KB-06)", () => {
  it("PUTs only the changed fields and, on success, toasts, closes and refreshes the dataset keys", async () => {
    const { client } = renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), " v2");
    await userEvent.click(submit());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(puts()).toHaveLength(1);
    expect(sentBody()).toEqual({ name: "Reports v2" });
    expect(await screen.findByText("Dataset settings saved")).toBeInTheDocument();
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetQueryKey("t1", "ds-1"))?.isInvalidated).toBe(true);
  });

  it("sends the visibility, a cleared description as null and a changed embedding model, and nothing else", async () => {
    renderDialog();
    await readyWithSelect();
    await userEvent.click(within(visibility()).getByRole("radio", { name: /Only me/ }));
    await userEvent.clear(descriptionField());
    await userEvent.selectOptions(embeddingField(), EMBED_B);
    await userEvent.click(submit());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(sentBody()).toEqual({ permission: "me", description: null, embd_id: EMBED_B });
  });

  it("sends one request for a double press", async () => {
    renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "!");
    await userEvent.dblClick(submit());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(puts()).toHaveLength(1);
  });

  it("puts duplicate_name under Name, names the dataset, focuses the field and keeps the dialog open", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 409, message: "a dataset with that name already exists", reason: "duplicate_name" };
    renderDialog();
    await readyWithSelect();
    await userEvent.clear(nameField());
    await userEvent.type(nameField(), "Taken");
    await userEvent.click(submit());
    const message = await screen.findByText('A dataset named "Taken" already exists in this workspace. Choose another name.');
    expect(screen.getByTestId("dataset-settings-dialog")).toContainElement(message);
    await waitFor(() => expect(nameField()).toHaveFocus());
    expect(nameField()).toHaveAttribute("aria-invalid", "true");
    expect(dialogState()).toHaveTextContent("open");
    expect(screen.queryByText("Dataset settings saved")).toBeNull();
  });

  it("puts model_unavailable under Embedding model and refetches the models", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 400, message: "model gone", reason: "model_unavailable" };
    renderDialog();
    await readyWithSelect();
    const before = calls.filter((c) => c.url === "/api/v1/models").length;
    models = [EMBED_A];
    await userEvent.selectOptions(embeddingField(), EMBED_B);
    await userEvent.click(submit());
    expect(await screen.findByText("That embedding model is no longer available in this workspace. Choose another one.")).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/v1/models").length).toBeGreaterThan(before));
    expect(embeddingField()).toHaveAttribute("aria-invalid", "true");
  });

  it("puts embedding_locked under Embedding model (documents arrived while the dialog was open)", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 409, message: "locked", reason: "embedding_locked" };
    const { client } = renderDialog();
    await readyWithSelect();
    await userEvent.selectOptions(embeddingField(), EMBED_B);
    await userEvent.click(submit());
    expect(await screen.findByText("This dataset has documents now, so its embedding model can't be changed.")).toBeInTheDocument();
    expect(dialogState()).toHaveTextContent("open");
    expect(client.getQueryState(datasetQueryKey("t1", "ds-1"))?.isInvalidated).toBe(true);
  });

  it("shows the search index message for a 503 index_unavailable", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 503, message: "index down", reason: "index_unavailable" };
    renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "!");
    await userEvent.click(submit());
    expect(await screen.findByTestId("dataset-settings-error")).toHaveTextContent(
      "The search index isn't available right now, so the settings weren't saved. Try again in a moment.",
    );
    expect(dialogState()).toHaveTextContent("open");
  });

  it("shows the fallback message for any other failure, as fixed copy rather than server text", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 500, message: "<img src=x onerror=alert(1)>" };
    renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "!");
    await userEvent.click(submit());
    const alert = await screen.findByTestId("dataset-settings-error");
    expect(alert).toHaveTextContent("The settings weren't saved. Try again.");
    expect(alert.querySelector("img")).toBeNull();
  });

  it("shows the lost-permission alert on a 403 and refetches the dataset and the lists (D-09, T-03-25-02)", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 403, message: "forbidden" };
    const { client } = renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "!");
    await userEvent.click(submit());
    expect(await screen.findByTestId("dataset-settings-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetQueryKey("t1", "ds-1"))?.isInvalidated).toBe(true);
    expect(dialogState()).toHaveTextContent("open");
  });

  it("clears an answer once the field it belongs to is edited", async () => {
    forced["PUT /api/v1/datasets/ds-1"] = { status: 409, message: "dup", reason: "duplicate_name" };
    renderDialog();
    await readyWithSelect();
    await userEvent.type(nameField(), "!");
    await userEvent.click(submit());
    await screen.findByText(/already exists in this workspace/);
    await userEvent.type(nameField(), "?");
    expect(screen.queryByText(/already exists in this workspace/)).toBeNull();
  });
});
