import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Outlet, RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { WorkspaceSwitch } from "@/components/workspace-switch";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import {
  DATASET_ID,
  OTHER_DATASET_ID,
  createDatasetServer,
  datasetRow,
  documentRow,
  membershipRow,
  storedMemberships,
  type DatasetRow,
} from "@/test/dataset-server";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { advanceParse } from "@/test/server-areas/files";
import DatasetPage from ".";

// Drives the real page, table, dialogs, hooks, services and HTTP client against an in-memory server shaped like the
// dataset, document and membership APIs. The router is a real memory router so navigation (and its `replace`) is visible.
const user = (over: Partial<SessionUser>): SessionUser => ({
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
  ...over,
});
const ADA = user({});

const server = createDatasetServer();
const originalAdapter = http.defaults.adapter;
let router: ReturnType<typeof createMemoryRouter>;

function Shell() {
  return (
    <>
      <WorkspaceSwitch />
      <Outlet />
    </>
  );
}

function renderPage(entry = `/dataset/files?id=${DATASET_ID}`) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  router = createMemoryRouter(
    [
      {
        element: <Shell />,
        children: [
          { path: "/dataset/files", element: <DatasetPage /> },
          { path: "/datasets", element: <p data-testid="gallery-page">gallery</p> },
        ],
      },
    ],
    { initialEntries: [entry] },
  );
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

/** Signs in `who` with the given membership rows; the active workspace is the user's own. */
function signIn(who: SessionUser, rows = server.memberships) {
  server.memberships = rows;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(who);
  useWorkspaceStore.getState().initialise(who.id, who.tenantId, storedMemberships(rows));
}

const location = () => `${router.state.location.pathname}${router.state.location.search}`;
const rows = () => screen.queryAllByTestId("document-row");
const detailCalls = () => server.callsTo("GET", `/api/v1/datasets/${DATASET_ID}`);
const documentCalls = () => server.callsTo("GET", `/api/v1/datasets/${DATASET_ID}/documents`);

beforeEach(() => {
  server.reset();
  server.datasets[DATASET_ID] = datasetRow();
  server.documents[DATASET_ID] = [documentRow(1), documentRow(2), documentRow(3)];
  signIn(ADA, [membershipRow("t1", "Ada's workspace", "owner", "Ada")]);
  setAuthorization("tok-session");
  http.defaults.adapter = server.adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Dataset workspace structure (UI-11)", () => {
  it("shows a back link, the name as the first heading, the meta line, the description and the title", async () => {
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    const back = within(page).getByTestId("dataset-back");
    expect(back).toHaveAttribute("href", "/datasets");
    expect(back).toHaveTextContent("Datasets");
    expect(within(page).getByRole("heading", { level: 1, name: "Reports" })).toBe(within(page).getAllByRole("heading")[0]);
    const meta = within(page).getByTestId("dataset-meta");
    expect(within(meta).getByText("Team")).toBeInTheDocument();
    expect(within(meta).getByText("3 documents")).toBeInTheDocument();
    expect(within(meta).getByText("Embedding model")).toBeInTheDocument();
    expect(within(meta).getByText("embed-one@OpenRouter").className).toContain("font-mono");
    expect(within(page).getByText("Quarterly reports")).toBeInTheDocument();
    expect(document.title).toBe("Reports - devRag");
    expect(await within(page).findByTestId("documents-table")).toBeInTheDocument();
  });

  it("shows 'Only me' and the singular count for a private dataset with one document", async () => {
    server.datasets[DATASET_ID] = datasetRow({ permission: "me" });
    server.documents[DATASET_ID] = [documentRow(1)];
    renderPage();
    const meta = await screen.findByTestId("dataset-meta");
    expect(within(meta).getByText("Only me")).toBeInTheDocument();
    expect(within(meta).getByText("1 document")).toBeInTheDocument();
  });

  it("renders the dataset name and description as text, never as markup", async () => {
    server.datasets[DATASET_ID] = datasetRow({ name: "<img src=x onerror=alert(1)>", description: "<b>bold</b>" });
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    expect(page.querySelector("img, b")).toBeNull();
    expect(within(page).getByRole("heading", { level: 1 })).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(document.title).toBe("<img src=x onerror=alert(1)> - devRag");
  });

  it("shows a header and table skeleton while the dataset loads", async () => {
    let release: () => void = () => {};
    server.holds[`GET /api/v1/datasets/${DATASET_ID}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderPage();
    expect(await screen.findByTestId("dataset-page-skeleton")).toBeInTheDocument();
    expect(screen.getByText("Loading dataset")).toBeInTheDocument();
    release();
    expect(await screen.findByTestId("dataset-page")).toBeInTheDocument();
  });

  it("shows a page-level error for a 5xx on the dataset, naming this dataset, with Try again", async () => {
    server.forced[`GET /api/v1/datasets/${DATASET_ID}`] = { status: 503, message: "down" };
    renderPage();
    const failed = await screen.findByTestId("error-state");
    expect(within(failed).getByRole("heading", { level: 1, name: "Couldn't load this dataset" })).toBeInTheDocument();
    expect(screen.queryByTestId("dataset-not-found")).toBeNull();
    delete server.forced[`GET /api/v1/datasets/${DATASET_ID}`];
    await userEvent.click(within(failed).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("dataset-page")).toBeInTheDocument();
  });

  it("keeps the header usable when only the documents fail, with an in-place error", async () => {
    server.forced[`GET /api/v1/datasets/${DATASET_ID}/documents`] = { status: 503, message: "down" };
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    const failed = await within(page).findByTestId("error-state");
    expect(within(failed).getByRole("heading", { name: "Couldn't load documents" })).toBeInTheDocument();
    expect(within(page).getByTestId("dataset-upload")).toBeInTheDocument();
    expect(within(page).getByRole("heading", { level: 1, name: "Reports" })).toBeInTheDocument();
  });

  it("shows the empty state with the only Upload files button when the dataset has no documents", async () => {
    server.documents[DATASET_ID] = [];
    renderPage();
    expect(await screen.findByRole("heading", { level: 2, name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Upload files" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(await screen.findByTestId("upload-dialog")).toBeInTheDocument();
  });

  it("keeps page and keywords in the URL and sends them with the request", async () => {
    server.documents[DATASET_ID] = Array.from({ length: 25 }, (_, i) => documentRow(i + 1));
    renderPage(`/dataset/files?id=${DATASET_ID}&page=2&keywords=report`);
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(0));
    expect(documentCalls().at(-1)?.params).toEqual({ page: 2, page_size: 20, keywords: "report" });
    await waitFor(() => expect(rows()).toHaveLength(5));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(router.state.location.search).toBe(`?id=${DATASET_ID}&keywords=report`));
  });
});

describe("Dataset not found (D-27, T-03-31-01)", () => {
  async function notFound() {
    const block = await screen.findByTestId("dataset-not-found");
    expect(within(block).getByRole("heading", { level: 1, name: "Dataset not found" })).toBeInTheDocument();
    expect(within(block).getByText("It may have been deleted, or it isn't shared with you.")).toBeInTheDocument();
    const action = within(block).getByRole("link", { name: "Back to datasets" });
    expect(action).toHaveAttribute("href", "/datasets");
    expect(screen.queryByTestId("dataset-back")).toBeNull();
    expect(screen.queryByTestId("dataset-actions")).toBeNull();
    expect(screen.queryByTestId("dataset-upload")).toBeNull();
    return block.textContent;
  }

  it("renders one identical block for an unknown id, a missing id and a malformed id", async () => {
    const texts: Array<string | null> = [];
    for (const entry of [`/dataset/files?id=${OTHER_DATASET_ID}`, "/dataset/files", "/dataset/files?id=not-a-real-id", "/dataset/files?id=%3Cscript%3E"]) {
      const view = renderPage(entry);
      texts.push(await notFound());
      view.unmount();
    }
    expect(new Set(texts).size).toBe(1);
  });

  it("sends no request for a missing or malformed id", async () => {
    for (const entry of ["/dataset/files", "/dataset/files?id=short", `/dataset/files?id=${DATASET_ID}0`, "/dataset/files?id=../../etc"]) {
      server.calls = [];
      const view = renderPage(entry);
      await notFound();
      expect(server.calls.filter((c) => (c.url ?? "").startsWith("/api/v1/datasets"))).toEqual([]);
      view.unmount();
    }
  });

  it("shows the same block for a private dataset of someone else (the server answers 404)", async () => {
    server.forced[`GET /api/v1/datasets/${DATASET_ID}`] = { status: 404, message: "not found" };
    renderPage();
    await notFound();
    expect(screen.queryByTestId("error-state")).toBeNull();
  });

  it("goes back to the gallery from the primary button", async () => {
    renderPage("/dataset/files");
    await userEvent.click(await screen.findByRole("link", { name: "Back to datasets" }));
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
  });

  it("shows the block, binds nothing and does not navigate when the dataset's workspace is not one the caller joined", async () => {
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t7" });
    renderPage();
    await notFound();
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    expect(location()).toBe(`/dataset/files?id=${DATASET_ID}`);
  });
});

describe("Who can do what (D-09, D-20, D-27)", () => {
  interface Actor {
    name: string;
    who: SessionUser;
    role: string;
    /** Whether the actor owns workspace t9 (the dataset's workspace) or joined it. */
    dataset: Partial<DatasetRow>;
    manages: boolean;
    deletable: number;
  }

  // Documents: report-01 uploaded by u2 (the dataset's creator), report-02 by u4.
  const ACTORS: Actor[] = [
    { name: "workspace owner", who: user({ id: "u1", tenantId: "t9", tenantName: "Grace's workspace" }), role: "owner", dataset: { tenant_id: "t9", created_by: "u2" }, manages: true, deletable: 2 },
    { name: "admin", who: user({ id: "u3", nickname: "Gil", tenantId: "t3", tenantName: "Gil's workspace" }), role: "admin", dataset: { tenant_id: "t9", created_by: "u2" }, manages: true, deletable: 2 },
    { name: "dataset creator", who: user({ id: "u2", nickname: "Cy", tenantId: "t2", tenantName: "Cy's workspace" }), role: "normal", dataset: { tenant_id: "t9", created_by: "u2" }, manages: true, deletable: 2 },
    { name: "other member", who: user({ id: "u4", nickname: "Dan", tenantId: "t4", tenantName: "Dan's workspace" }), role: "normal", dataset: { tenant_id: "t9", created_by: "u2" }, manages: false, deletable: 1 },
  ];

  for (const actor of ACTORS) {
    it(`${actor.name}: actions menu ${actor.manages ? "present" : "absent"}, ${actor.deletable} delete icon(s), Upload files visible`, async () => {
      const ownsIt = actor.who.tenantId === "t9";
      signIn(
        actor.who,
        ownsIt
          ? [membershipRow("t9", "Grace's workspace", "owner", "Grace")]
          : [membershipRow(actor.who.tenantId, actor.who.tenantName, "owner", actor.who.nickname), membershipRow("t9", "Grace's workspace", actor.role, "Grace")],
      );
      useWorkspaceStore.getState().setActive("t9");
      server.datasets[DATASET_ID] = datasetRow(actor.dataset);
      server.documents[DATASET_ID] = [documentRow(1, { created_by: "u2" }), documentRow(2, { created_by: "u4" })];
      renderPage();
      await screen.findByTestId("documents-table");
      expect(screen.getByTestId("dataset-upload")).toBeInTheDocument();
      expect(screen.queryAllByTestId("dataset-actions")).toHaveLength(actor.manages ? 1 : 0);
      expect(screen.queryAllByTestId("document-delete")).toHaveLength(actor.deletable);
    });
  }

  it("opens the settings dialog from the menu", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-actions"));
    await userEvent.click(await screen.findByTestId("dataset-menu-settings"));
    expect(await screen.findByTestId("dataset-settings-dialog")).toBeInTheDocument();
  });

  it("opens the default chunking method dialog from the menu, saves it and returns focus to the menu button", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-actions"));
    expect(within(await screen.findByTestId("dataset-menu")).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Default chunking method", "Dataset settings", "Delete dataset"]);
    await userEvent.click(screen.getByTestId("dataset-menu-chunking"));
    const dialog = await screen.findByTestId("chunk-method-dialog");
    const size = await within(dialog).findByTestId("field-chunk-size");
    await userEvent.clear(size);
    await userEvent.type(size, "300");
    await userEvent.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    await waitFor(() => expect(screen.getByTestId("dataset-actions")).toHaveFocus());
    expect(server.callsTo("PUT", `/api/v1/datasets/${DATASET_ID}`)).toHaveLength(1);
  });

  it("deletes the dataset from the menu, goes to /datasets and never asks for the deleted dataset again", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-actions"));
    await userEvent.click(await screen.findByTestId("dataset-menu-delete"));
    const confirm = await screen.findByTestId("dataset-delete-confirm");
    await waitFor(() => expect(confirm).not.toHaveAttribute("aria-disabled"));
    const before = detailCalls().length;
    await userEvent.click(confirm);
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
    expect(location()).toBe("/datasets");
    expect(detailCalls().length).toBe(before);
    expect(server.datasets[DATASET_ID]).toBeUndefined();
  });

  it("updates the document count in the meta line after a document is deleted", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rows()[0] as HTMLElement).getByTestId("document-delete"));
    await userEvent.click(await screen.findByTestId("document-delete-confirm"));
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(await within(screen.getByTestId("dataset-meta")).findByText("2 documents")).toBeInTheDocument();
  });
});

describe("Upload files (UI-12, DOC-01)", () => {
  const file = (name = "notes.txt") => new File(["hello"], name, { type: "text/plain" });

  it("opens the dialog from the header button with the dataset's limits", async () => {
    server.datasets[DATASET_ID] = datasetRow({
      upload_limits: { max_file_bytes: 5 * 1024 * 1024, max_files_per_request: 4, max_documents: 50, allowed_extensions: ["txt", "pdf"] },
    });
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-upload"));
    const dialog = await screen.findByTestId("upload-dialog");
    expect(within(dialog).getByRole("heading", { name: "Upload files to Reports" })).toBeInTheDocument();
    expect(within(dialog).getByText(/Up to 5 MB per file, 4 files at a time\./)).toBeInTheDocument();
  });

  it("refetches the table after an upload succeeds and shows the new document", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-upload"));
    await screen.findByTestId("upload-dialog");
    await userEvent.upload(screen.getByTestId("upload-input"), file("fresh-upload.txt"));
    await userEvent.click(screen.getByTestId("upload-submit"));
    await waitFor(() => expect(screen.getByText("fresh-upload.txt", { selector: "td *, td" })).toBeInTheDocument());
    expect(rows()).toHaveLength(4);
    expect(await within(screen.getByTestId("dataset-meta")).findByText("4 documents")).toBeInTheDocument();
  });

  it("shows the drop overlay for a file drag, hides it when the drag leaves, and ignores a drag without files", async () => {
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    expect(screen.queryByTestId("dataset-drop-overlay")).toBeNull();
    fireEvent.dragEnter(page, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(screen.queryByTestId("dataset-drop-overlay")).toBeNull();
    fireEvent.dragEnter(page, { dataTransfer: { types: ["Files"], files: [] } });
    const overlay = await screen.findByTestId("dataset-drop-overlay");
    expect(overlay).toHaveTextContent("Drop files to upload to Reports");
    expect(overlay.className).toContain("border-2");
    expect(overlay.className).toContain("border-primary");
    expect(overlay.className).toContain("bg-background/80");
    fireEvent.dragLeave(page, { dataTransfer: { types: ["Files"], files: [] } });
    await waitFor(() => expect(screen.queryByTestId("dataset-drop-overlay")).toBeNull());
  });

  it("prevents the browser from opening a dropped file and opens the dialog with the files queued", async () => {
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    const dropped = file("dropped.txt");
    const transfer = { types: ["Files"], files: [dropped] };
    fireEvent.dragEnter(page, { dataTransfer: transfer });
    const notPrevented = fireEvent.dragOver(page, { dataTransfer: transfer });
    expect(notPrevented).toBe(false);
    const dropNotPrevented = fireEvent.drop(page, { dataTransfer: transfer });
    expect(dropNotPrevented).toBe(false);
    const dialog = await screen.findByTestId("upload-dialog");
    expect(within(dialog).getAllByTestId("upload-row")).toHaveLength(1);
    expect(within(dialog).getByText("dropped.txt")).toBeInTheDocument();
    expect(screen.queryByTestId("dataset-drop-overlay")).toBeNull();
  });

  it("leaves a drag without files alone (not prevented, no dialog)", async () => {
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    const transfer = { types: ["text/uri-list"], files: [] };
    expect(fireEvent.dragOver(page, { dataTransfer: transfer })).toBe(true);
    expect(fireEvent.drop(page, { dataTransfer: transfer })).toBe(true);
    expect(screen.queryByTestId("upload-dialog")).toBeNull();
  });

  it("does not queue the previous drop again when the dialog is opened from the button", async () => {
    renderPage();
    const page = await screen.findByTestId("dataset-page");
    fireEvent.drop(page, { dataTransfer: { types: ["Files"], files: [file("first.txt")] } });
    const dialog = await screen.findByTestId("upload-dialog");
    expect(within(dialog).getAllByTestId("upload-row")).toHaveLength(1);
    await userEvent.click(within(dialog).getByTestId("upload-close"));
    await waitFor(() => expect(screen.queryByTestId("upload-dialog")).toBeNull());
    await userEvent.click(screen.getByTestId("dataset-upload"));
    const again = await screen.findByTestId("upload-dialog");
    expect(within(again).queryAllByTestId("upload-row")).toHaveLength(0);
  });

  it("does not react to drags inside an open dialog (the dialog's own dropzone handles them)", async () => {
    renderPage();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("dataset-upload"));
    const zone = await screen.findByTestId("upload-dropzone");
    fireEvent.dragEnter(zone, { dataTransfer: { types: ["Files"], files: [] } });
    expect(screen.queryByTestId("dataset-drop-overlay")).toBeNull();
  });
});

describe("Workspace binding (D-26)", () => {
  const JOINED = [membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")];

  function deepLink() {
    signIn(ADA, JOINED);
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t9", created_by: "u1" });
    return renderPage();
  }

  it("deep link into a joined workspace stays on the page", async () => {
    deepLink();
    await screen.findByTestId("dataset-page");
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    expect(await screen.findByTestId("documents-table")).toBeInTheDocument();
    expect(location()).toBe(`/dataset/files?id=${DATASET_ID}`);
    expect(router.state.historyAction).toBe("POP");
    expect(screen.queryByTestId("gallery-page")).toBeNull();
    expect(screen.getByTestId("workspace-switch")).toHaveTextContent("Grace's workspace");
    expect(screen.getByTestId("workspace-announcer")).toHaveTextContent("Switched to Grace's workspace");
  });

  it("does not loop: after the switch settles the page is still shown, at the same location, with a bounded number of requests", async () => {
    deepLink();
    await screen.findByTestId("documents-table");
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    await act(async () => {});
    expect(screen.getByTestId("dataset-page")).toBeInTheDocument();
    expect(location()).toBe(`/dataset/files?id=${DATASET_ID}`);
    expect(detailCalls().length).toBeLessThanOrEqual(2);
    expect(documentCalls().length).toBeLessThanOrEqual(2);
  });

  it("a later user switch navigates to /datasets with replace", async () => {
    deepLink();
    await screen.findByTestId("documents-table");
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    act(() => useWorkspaceStore.getState().setActive("t1"));
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
    expect(location()).toBe("/datasets");
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("a user switch away from the workspace of an own dataset navigates too", async () => {
    signIn(ADA, JOINED);
    renderPage();
    await screen.findByTestId("documents-table");
    act(() => useWorkspaceStore.getState().setActive("t9"));
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("opening a dataset of the already active workspace sets nothing and navigates nowhere", async () => {
    signIn(ADA, JOINED);
    renderPage();
    await screen.findByTestId("documents-table");
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    expect(screen.getByTestId("workspace-announcer")).toBeEmptyDOMElement();
    expect(location()).toBe(`/dataset/files?id=${DATASET_ID}`);
    expect(router.state.historyAction).toBe("POP");
  });
});

describe("Parsing on the workspace page (KB-14, KB-19, UI-SPEC states)", () => {
  const DOCS = `/api/v1/datasets/${DATASET_ID}/documents`;

  it("reads the chunk count in the meta line in the singular and plural forms", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 1 })];
    const first = renderPage();
    expect(await within(await screen.findByTestId("dataset-meta")).findByText("1 chunk")).toBeInTheDocument();
    first.unmount();
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 4 }), documentRow(2, { run: "3", chunk_num: 3 })];
    renderPage();
    expect(await within(await screen.findByTestId("dataset-meta")).findByText("7 chunks")).toBeInTheDocument();
  });

  it("refreshes the meta line and the summary once when a row leaves Parsing", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.4 })];
    renderPage();
    const meta = await screen.findByTestId("dataset-meta");
    await within(meta).findByText("0 chunks");
    act(() => advanceParse(server, documentRow(1).id, { run: "3", progress: 1, chunkCount: 5 }));
    expect(await within(meta).findByText("5 chunks", {}, { timeout: 6000 })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("summary-count-done")).toHaveTextContent("1"));
  }, 15000);

  it("says live updates are paused after three failed polls in a row, keeps the rows, and removes the notice on the next success", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.4 })];
    renderPage();
    await screen.findByTestId("documents-table");
    expect(screen.queryByTestId("documents-poll-paused")).toBeNull();
    server.forced[`GET ${DOCS}`] = { status: 500, message: "down" };
    const notice = await screen.findByTestId("documents-poll-paused", {}, { timeout: 12000 });
    expect(notice).toHaveTextContent("Live updates are paused. The status below may be out of date.");
    expect(screen.getByTestId("documents-table")).toBeInTheDocument();
    expect(screen.getByTestId("document-progress")).toHaveTextContent("40%");
    expect(screen.queryByTestId("error-state")).toBeNull();
    delete server.forced[`GET ${DOCS}`];
    await userEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByTestId("documents-poll-paused")).toBeNull());
  }, 25000);

  it("announces started, finished, failed and cancelled in one polite region, never a percentage and never on the first render", async () => {
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2, { run: "1", progress: 0.2 }), documentRow(3, { run: "1", progress: 0.2 })];
    renderPage();
    await screen.findByTestId("documents-table");
    const live = screen.getByTestId("documents-live");
    expect(live).toHaveAttribute("role", "status");
    expect(live).toHaveTextContent("");
    await userEvent.click(within(rows()[0] as HTMLElement).getByTestId("document-parse"));
    await waitFor(() => expect(live).toHaveTextContent("report-01.pdf: parsing started"));
    act(() => {
      advanceParse(server, documentRow(2).id, { run: "3", progress: 1, chunkCount: 2 });
      advanceParse(server, documentRow(3).id, { run: "4", progress: 0.5, error: { step: "chunk", code: "no_readable_text", message: "" } });
    });
    await waitFor(() => expect(live).toHaveTextContent("report-02.pdf: parsing finished, 2 chunks"), { timeout: 6000 });
    expect(live).toHaveTextContent("report-03.pdf: parsing failed");
    expect(live.textContent).not.toContain("%");
    act(() => advanceParse(server, documentRow(1).id, { run: "2" }));
    await waitFor(() => expect(live).toHaveTextContent("report-01.pdf: parsing cancelled"), { timeout: 6000 });
    expect(live.textContent).not.toContain("%");
  }, 25000);

  it("keeps the search text, the page and the selection through polls", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.1 }), documentRow(2)];
    renderPage(`/dataset/files?id=${DATASET_ID}&keywords=report`);
    await screen.findByTestId("documents-table");
    const field = screen.getByRole("searchbox", { name: "Search documents" });
    expect(field).toHaveValue("report");
    await userEvent.click(within(rows()[1] as HTMLElement).getByTestId("document-select"));
    const where = location();
    act(() => advanceParse(server, documentRow(1).id, { run: "1", progress: 0.7, message: "later" }));
    await waitFor(() => expect(within(rows()[0] as HTMLElement).getByTestId("document-progress")).toHaveTextContent("70%"), { timeout: 6000 });
    expect(screen.getByRole("searchbox", { name: "Search documents" })).toHaveValue("report");
    expect(location()).toBe(where);
    expect(screen.getByTestId("selection-count")).toHaveTextContent("1 document selected");
  }, 15000);
});
