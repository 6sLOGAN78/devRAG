import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeleteDatasetDialog } from "@/components/delete-dataset-dialog";
import { DeleteDocumentDialog } from "@/components/delete-document-dialog";
import { Toaster } from "@/components/ui/sonner";
import { documentsQueryKey } from "@/hooks/use-document-request";
import { datasetQueryKey, datasetsQueryKey } from "@/hooks/use-knowledge-request";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";

// Drives the real dialogs, hooks, services and HTTP client against an in-memory server shaped like plans 03-17 and
// 03-18: the dataset detail (fresh document count), the all-or-nothing dataset delete and the document delete.
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

const DATASET = { id: "ds-1", name: "Reports", tenantId: "t1" };
const DOCUMENT = { id: "doc-1", name: "plan.pdf" };

interface Forced {
  status: number;
  message: string;
  reason?: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let forced: Record<string, Forced> = {};
let docNum = 3;
let hold: Promise<void> | null = null;
let deleteGate: Promise<void> | null = null;

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const data = f.reason === undefined ? null : { reason: f.reason };
  const response = { data: { code: f.status, message: f.message, data }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

function detail(config: InternalAxiosRequestConfig) {
  return ok(config, {
    id: DATASET.id,
    name: DATASET.name,
    description: "",
    permission: "team",
    embd_id: "embed-one@OpenRouter",
    embedding_dimension: 8,
    doc_num: docNum,
    chunk_num: 0,
    created_by: "u1",
    tenant_id: "t1",
    update_time: 1760000000000,
  });
}

async function serve(config: InternalAxiosRequestConfig): Promise<unknown> {
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  if (key === "GET /api/v1/datasets/ds-1" && hold) await hold;
  if (key === "DELETE /api/v1/datasets" && deleteGate) await deleteGate;
  const stop = forced[key];
  if (stop) return failure(config, stop);
  if (key === "GET /v1/tenant/list") return ok(config, []);
  if (key === "GET /api/v1/datasets/ds-1") return detail(config);
  if (key === "DELETE /api/v1/datasets") return ok(config, { deleted: [DATASET.id] });
  if (key === "DELETE /api/v1/datasets/ds-1/documents") return ok(config, { deleted: 1 });
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  return serve(config) as never;
};

const callsTo = (method: string, url: string) => calls.filter((c) => c.method?.toUpperCase() === method && c.url === url);
const bodyOf = (config: InternalAxiosRequestConfig | undefined) => JSON.parse(String(config?.data)) as Record<string, unknown>;

interface DatasetHarnessProps {
  dataset?: { id: string; name: string; tenantId: string };
  onSuccess?: () => void;
}

function DatasetHarness({ dataset = DATASET, onSuccess }: DatasetHarnessProps) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <DeleteDatasetDialog dataset={dataset} open={open} onOpenChange={setOpen} onSuccess={onSuccess} />
      <p data-testid="dialog-state">{open ? "open" : "closed"}</p>
    </>
  );
}

function DocumentHarness({ onSuccess }: { onSuccess?: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <DeleteDocumentDialog datasetId={DATASET.id} datasetName={DATASET.name} document={DOCUMENT} open={open} onOpenChange={setOpen} onSuccess={onSuccess} />
      <p data-testid="dialog-state">{open ? "open" : "closed"}</p>
    </>
  );
}

function renderWith(ui: React.ReactElement, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  registerQueryClient(client);
  const view = render(
    <QueryClientProvider client={client}>
      {ui}
      <Toaster />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

beforeEach(() => {
  calls = [];
  forced = {};
  docNum = 3;
  hold = null;
  deleteGate = null;
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

const confirmButton = () => screen.getByTestId("dataset-delete-confirm");
const dialogState = () => screen.getByTestId("dialog-state");

describe("Delete dataset dialog: the document count (D-10, T-03-25-03)", () => {
  it("keeps Delete dataset aria-disabled with a skeleton line until the count loads, and sends nothing when pressed early", async () => {
    let release: () => void = () => {};
    hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderWith(<DatasetHarness />);
    const dialog = await screen.findByTestId("dataset-delete-dialog");
    expect(within(dialog).getByRole("heading", { name: "Delete dataset?" })).toBeInTheDocument();
    expect(confirmButton()).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("dataset-delete-count-skeleton")).toBeInTheDocument();
    await userEvent.click(confirmButton());
    expect(callsTo("DELETE", "/api/v1/datasets")).toHaveLength(0);
    release();
    await screen.findByText(/and its 3 documents will be permanently deleted/);
    expect(confirmButton()).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByTestId("dataset-delete-count-skeleton")).toBeNull();
  });

  it("states many, one and no documents in the three bodies, naming the dataset", async () => {
    for (const [count, text] of [
      [5, '"Reports" and its 5 documents will be permanently deleted, together with their stored files and the dataset\'s search index. This can\'t be undone.'],
      [1, '"Reports" and its 1 document will be permanently deleted, together with its stored file and the dataset\'s search index. This can\'t be undone.'],
      [0, '"Reports" has no documents. The dataset and its search index will be permanently deleted. This can\'t be undone.'],
    ] as const) {
      docNum = count;
      const view = renderWith(<DatasetHarness />);
      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(screen.getByTestId("dataset-delete-count")).toHaveTextContent(text);
      view.unmount();
    }
  });

  it("loads a fresh count even when a stale one is cached, and does not enable Delete on the stale one", async () => {
    let release: () => void = () => {};
    hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    docNum = 7;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(datasetQueryKey("t1", DATASET.id), { ...DATASET, docNum: 2, chunkNum: 0 });
    renderWith(<DatasetHarness />, client);
    await screen.findByTestId("dataset-delete-dialog");
    expect(confirmButton()).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByText(/and its 2 documents/)).toBeNull();
    release();
    await screen.findByText(/and its 7 documents will be permanently deleted/);
    expect(confirmButton()).not.toHaveAttribute("aria-disabled");
  });

  it("shows 'Couldn't load the document count.' with Try again when the detail fails, keeps Delete disabled, and recovers on retry", async () => {
    forced["GET /api/v1/datasets/ds-1"] = { status: 500, message: "boom" };
    renderWith(<DatasetHarness />);
    expect(await screen.findByText("Couldn't load the document count.")).toBeInTheDocument();
    expect(confirmButton()).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(confirmButton());
    expect(callsTo("DELETE", "/api/v1/datasets")).toHaveLength(0);
    delete forced["GET /api/v1/datasets/ds-1"];
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText(/and its 3 documents will be permanently deleted/);
    expect(confirmButton()).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByText("Couldn't load the document count.")).toBeNull();
  });

  it("gives initial focus to Keep dataset and closes on it without deleting", async () => {
    renderWith(<DatasetHarness />);
    await screen.findByText(/and its 3 documents/);
    const keep = screen.getByRole("button", { name: "Keep dataset" });
    expect(keep).toHaveFocus();
    await userEvent.click(keep);
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(callsTo("DELETE", "/api/v1/datasets")).toHaveLength(0);
  });

  it("renders a hostile dataset name as text", async () => {
    const name = '<img src=x onerror="alert(1)">';
    renderWith(<DatasetHarness dataset={{ ...DATASET, name }} />);
    const body = await screen.findByTestId("dataset-delete-count");
    await waitFor(() => expect(body.textContent).toContain(`"${name}" and its 3 documents`));
    expect(body.querySelector("img")).toBeNull();
  });
});

describe("Delete dataset dialog: deleting (KB-07, D-10)", () => {
  it("sends DELETE {ids:[id], tenant_id}, toasts 'Dataset deleted', closes, calls onSuccess and refreshes the lists", async () => {
    const onSuccess = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
    renderWith(<DatasetHarness onSuccess={onSuccess} />, client);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    const sent = callsTo("DELETE", "/api/v1/datasets");
    expect(sent).toHaveLength(1);
    expect(bodyOf(sent[0])).toEqual({ ids: ["ds-1"], tenant_id: "t1" });
    expect(await screen.findByText("Dataset deleted")).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
    expect(client.getQueryData(datasetQueryKey("t1", DATASET.id))).toBeUndefined();
    // The deleted dataset's detail is not asked for again (it would answer 404).
    expect(callsTo("GET", "/api/v1/datasets/ds-1")).toHaveLength(1);
  });

  it("keeps the dialog open and the button busy while the server answers, and sends one request for a double press", async () => {
    let release: () => void = () => {};
    deleteGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderWith(<DatasetHarness />);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    await userEvent.click(confirmButton());
    await waitFor(() => expect(confirmButton()).toHaveAttribute("aria-busy", "true"));
    expect(dialogState()).toHaveTextContent("open");
    expect(callsTo("DELETE", "/api/v1/datasets")).toHaveLength(1);
    release();
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(callsTo("DELETE", "/api/v1/datasets")).toHaveLength(1);
  });

  it("shows the inline failure message on a server error and stays open without toasting success", async () => {
    forced["DELETE /api/v1/datasets"] = { status: 500, message: "boom" };
    const onSuccess = vi.fn();
    renderWith(<DatasetHarness onSuccess={onSuccess} />);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    const alert = await screen.findByTestId("dataset-delete-error");
    expect(alert).toHaveTextContent("The dataset wasn't deleted. Nothing was removed. Try again.");
    expect(dialogState()).toHaveTextContent("open");
    expect(screen.queryByText("Dataset deleted")).toBeNull();
    expect(onSuccess).not.toHaveBeenCalled();
    // The same dialog can try again.
    delete forced["DELETE /api/v1/datasets"];
    await userEvent.click(confirmButton());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows the search index message for a 503 index_unavailable", async () => {
    forced["DELETE /api/v1/datasets"] = { status: 503, message: "index down", reason: "index_unavailable" };
    renderWith(<DatasetHarness />);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    expect(await screen.findByTestId("dataset-delete-error")).toHaveTextContent(
      "The search index isn't available right now, so nothing was deleted. Try again in a moment.",
    );
    expect(dialogState()).toHaveTextContent("open");
  });

  it("shows the lost-permission alert on a 403, refetches the lists and the dataset, and does not delete (D-09, T-03-25-02)", async () => {
    forced["DELETE /api/v1/datasets"] = { status: 403, message: "forbidden" };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
    renderWith(<DatasetHarness />, client);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    expect(await screen.findByTestId("dataset-delete-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
    expect(dialogState()).toHaveTextContent("open");
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
    await waitFor(() => expect(callsTo("GET", "/api/v1/datasets/ds-1").length).toBeGreaterThan(1));
    expect(screen.queryByText("Dataset deleted")).toBeNull();
  });

  it("treats a 404 (already deleted elsewhere) as gone: refreshes the lists, closes and calls onSuccess without a success toast", async () => {
    forced["DELETE /api/v1/datasets"] = { status: 404, message: "not found" };
    const onSuccess = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
    renderWith(<DatasetHarness onSuccess={onSuccess} />, client);
    await screen.findByText(/and its 3 documents/);
    await userEvent.click(confirmButton());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Dataset deleted")).toBeNull();
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
  });
});

describe("Delete document dialog (DOC-14, checker flag 4)", () => {
  const confirm = () => screen.getByTestId("document-delete-confirm");

  it("names the document and the dataset, and gives initial focus to Keep document", async () => {
    renderWith(<DocumentHarness />);
    const dialog = await screen.findByTestId("document-delete-dialog");
    expect(within(dialog).getByRole("heading", { name: "Delete document?" })).toBeInTheDocument();
    expect(within(dialog).getByText('"plan.pdf" will be removed from Reports. This can\'t be undone.')).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep document" })).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "Delete document" })).toBeInTheDocument();
  });

  it("sends DELETE {ids:[id]}, toasts 'Document deleted', refetches the pages and both dataset keys, closes and calls onSuccess", async () => {
    const onSuccess = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(documentsQueryKey("t1", DATASET.id, 1, ""), { items: [], total: 0 });
    client.setQueryData(datasetQueryKey("t1", DATASET.id), { ...DATASET, docNum: 1, chunkNum: 0 });
    client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
    renderWith(<DocumentHarness onSuccess={onSuccess} />, client);
    await screen.findByTestId("document-delete-dialog");
    await userEvent.click(confirm());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    const sent = callsTo("DELETE", "/api/v1/datasets/ds-1/documents");
    expect(sent).toHaveLength(1);
    expect(bodyOf(sent[0])).toEqual({ ids: ["doc-1"] });
    expect(await screen.findByText("Document deleted")).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(client.getQueryState(documentsQueryKey("t1", DATASET.id, 1, ""))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetQueryKey("t1", DATASET.id))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
  });

  it("shows 'The document wasn't deleted. Nothing was removed. Try again.' inline and stays open on a failure", async () => {
    forced["DELETE /api/v1/datasets/ds-1/documents"] = { status: 500, message: "boom" };
    const onSuccess = vi.fn();
    renderWith(<DocumentHarness onSuccess={onSuccess} />);
    await screen.findByTestId("document-delete-dialog");
    await userEvent.click(confirm());
    expect(await screen.findByTestId("document-delete-error")).toHaveTextContent("The document wasn't deleted. Nothing was removed. Try again.");
    expect(dialogState()).toHaveTextContent("open");
    expect(screen.queryByText("Document deleted")).toBeNull();
    expect(onSuccess).not.toHaveBeenCalled();
    delete forced["DELETE /api/v1/datasets/ds-1/documents"];
    await userEvent.click(confirm());
    await waitFor(() => expect(dialogState()).toHaveTextContent("closed"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows the lost-permission alert on a 403 and refetches", async () => {
    forced["DELETE /api/v1/datasets/ds-1/documents"] = { status: 403, message: "forbidden" };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(documentsQueryKey("t1", DATASET.id, 1, ""), { items: [], total: 0 });
    renderWith(<DocumentHarness />, client);
    await screen.findByTestId("document-delete-dialog");
    await userEvent.click(confirm());
    expect(await screen.findByTestId("document-delete-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
    expect(client.getQueryState(documentsQueryKey("t1", DATASET.id, 1, ""))?.isInvalidated).toBe(true);
    expect(dialogState()).toHaveTextContent("open");
  });

  it("renders a hostile document name as text and sends one request for a double press", async () => {
    const name = "<script>alert(1)</script>";
    const GateHarness = () => {
      const [open, setOpen] = useState(true);
      return <DeleteDocumentDialog datasetId={DATASET.id} datasetName={DATASET.name} document={{ id: DOCUMENT.id, name }} open={open} onOpenChange={setOpen} />;
    };
    renderWith(<GateHarness />);
    const dialog = await screen.findByTestId("document-delete-dialog");
    expect(dialog.textContent).toContain(`"${name}" will be removed from Reports.`);
    expect(dialog.querySelector("script")).toBeNull();
    await userEvent.dblClick(confirm());
    await waitFor(() => expect(callsTo("DELETE", "/api/v1/datasets/ds-1/documents").length).toBeGreaterThan(0));
    expect(callsTo("DELETE", "/api/v1/datasets/ds-1/documents")).toHaveLength(1);
  });
});
