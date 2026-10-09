import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { ApiError, http, registerQueryClient } from "@/services/http";
import {
  DATASET_ID,
  UPDATED,
  createDatasetServer,
  datasetRow,
  documentRow,
  membershipRow,
  storedMemberships,
} from "@/test/dataset-server";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { DocumentStatusBadge } from "./document-status-badge";
import { DatasetFiles } from "./dataset-files";
import { datasetPageState } from "./errors";

// Renders the document table alone: real hooks, services and HTTP client against an in-memory server, no page around it.
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

const server = createDatasetServer();
const originalAdapter = http.defaults.adapter;
const DATASET = { id: DATASET_ID, name: "Reports", createdBy: "u1", tenantId: "t1" };

interface HarnessProps {
  initialPage?: number;
  initialKeywords?: string;
  onUpload?: () => void;
  onEmptyChange?: (empty: boolean) => void;
}

function Harness({ initialPage = 1, initialKeywords = "", onUpload = () => {}, onEmptyChange }: HarnessProps) {
  const [page, setPage] = useState(initialPage);
  const [keywords, setKeywords] = useState(initialKeywords);
  return (
    <>
      <DatasetFiles
        dataset={DATASET}
        limits={null}
        page={page}
        keywords={keywords}
        onPageChange={setPage}
        onSearch={(next) => {
          setKeywords(next);
          setPage(1);
        }}
        onUpload={onUpload}
        onEmptyChange={onEmptyChange}
      />
      <p data-testid="state">{`${page}|${keywords}`}</p>
    </>
  );
}

function renderTable(props: HarnessProps = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  const view = render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
      <Toaster />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const docs = (count: number) => Array.from({ length: count }, (_, i) => documentRow(i + 1));
const listCalls = () => server.callsTo("GET", `/api/v1/datasets/${DATASET_ID}/documents`);
const rows = () => screen.queryAllByTestId("document-row");
const state = () => screen.getByTestId("state").textContent;

beforeEach(() => {
  server.reset();
  server.memberships = [membershipRow("t1", "Ada's workspace", "owner", "Ada")];
  server.datasets[DATASET_ID] = datasetRow();
  server.documents[DATASET_ID] = docs(3);
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(server.memberships));
  setAuthorization("tok-session");
  http.defaults.adapter = server.adapter;
});
afterEach(() => {
  vi.useRealTimers();
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Document table structure (UI-11)", () => {
  it("is a table with a screen-reader caption, six scoped column headers and one row per document", async () => {
    renderTable();
    const table = await screen.findByTestId("documents-table");
    expect(table.tagName).toBe("TABLE");
    expect(within(table).getByText("Documents in Reports").tagName).toBe("CAPTION");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["Name", "Size", "Uploaded", "Status", "Progress", "Actions"]);
    for (const header of headers) expect(header).toHaveAttribute("scope", "col");
    expect(rows()).toHaveLength(3);
  });

  it("draws name with an icon and its full text in title, size, a dated <time>, the status badge and the progress", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { name: "A very long quarterly report name.pdf", size: 1536 })];
    renderTable();
    const row = (await screen.findAllByTestId("document-row"))[0] as HTMLElement;
    const name = within(row).getByText("A very long quarterly report name.pdf");
    expect(name).toHaveAttribute("title", "A very long quarterly report name.pdf");
    expect(name.className).toContain("break-all");
    expect(name.className).toContain("line-clamp-2");
    expect(within(row).getByText("1.5 KB").className).toContain("tabular-nums");
    const time = row.querySelector("time") as HTMLTimeElement;
    expect(time.getAttribute("datetime")).toBe(new Date(UPDATED).toISOString());
    expect(time.textContent).toBe(new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(UPDATED)));
    expect(within(row).getByTestId("document-status")).toHaveTextContent("Not started");
    expect(within(row).getByTestId("document-progress")).toHaveTextContent("0%");
    expect(within(row).getByTestId("document-progress").className).toContain("tabular-nums");
  });

  it("shows 'Unknown status' as an outline badge for any run value other than 0, never a Parse control", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1" }), documentRow(2, { run: "DONE" }), documentRow(3)];
    renderTable();
    await screen.findByTestId("documents-table");
    const statuses = screen.getAllByTestId("document-status").map((s) => s.textContent);
    expect(statuses).toEqual(["Unknown status", "Unknown status", "Not started"]);
    expect(screen.queryByRole("button", { name: /parse/i })).toBeNull();
    expect(screen.queryByText(/coming/i)).toBeNull();
  });

  it("renders file names as text, never as markup", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { name: "<img src=x onerror=alert(1)>.pdf" })];
    renderTable();
    const table = await screen.findByTestId("documents-table");
    expect(table.querySelector("img, script, b")).toBeNull();
    expect(within(table).getByText("<img src=x onerror=alert(1)>.pdf")).toBeInTheDocument();
  });

  it("shows a header row and five skeleton rows with a status line while loading", async () => {
    let release: () => void = () => {};
    server.holds[`GET /api/v1/datasets/${DATASET_ID}/documents`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderTable();
    expect(await screen.findAllByTestId("document-row-skeleton")).toHaveLength(5);
    expect(screen.getByText("Loading documents")).toBeInTheDocument();
    release();
    await screen.findByTestId("documents-table");
    expect(screen.queryAllByTestId("document-row-skeleton")).toHaveLength(0);
  });
});

describe("DocumentStatusBadge (UI-SPEC choice 22)", () => {
  it("renders 'Not started' for run 0 and 'Unknown status' for anything else", () => {
    const { rerender } = render(<DocumentStatusBadge run="0" />);
    expect(screen.getByText("Not started")).toBeInTheDocument();
    rerender(<DocumentStatusBadge run="3" />);
    expect(screen.getByText("Unknown status")).toBeInTheDocument();
    rerender(<DocumentStatusBadge run="" />);
    expect(screen.getByText("Unknown status")).toBeInTheDocument();
  });
});

describe("datasetPageState", () => {
  it("maps a 404 to notFound and everything else to error", () => {
    const answer = (status: number) => new ApiError({ code: status, message: "x", status });
    expect(datasetPageState(answer(404))).toBe("notFound");
    expect(datasetPageState(answer(500))).toBe("error");
    expect(datasetPageState(answer(503))).toBe("error");
    expect(datasetPageState(new Error("offline"))).toBe("error");
  });
});

describe("Empty, no-match and error states", () => {
  it("shows 'No documents yet' with the size limit, an Upload files action and no toolbar, and reports it", async () => {
    server.documents[DATASET_ID] = [];
    const onUpload = vi.fn();
    const onEmptyChange = vi.fn();
    renderTable({ onUpload, onEmptyChange });
    expect(await screen.findByRole("heading", { level: 2, name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByText("Upload PDF, Word, PowerPoint, Excel, text, Markdown, HTML, CSV, JSON, EPUB, JPG, PNG, MP3 or WAV files, up to 100 MB each.")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onEmptyChange).toHaveBeenLastCalledWith(true);
  });

  it("reports not-empty once documents are listed", async () => {
    const onEmptyChange = vi.fn();
    renderTable({ onEmptyChange });
    await screen.findByTestId("documents-table");
    expect(onEmptyChange).toHaveBeenLastCalledWith(false);
  });

  it("searches after the debounce, shows 'No documents match' with the body and Clear search, and clears it", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    const field = screen.getByRole("searchbox", { name: "Search documents" });
    vi.useFakeTimers();
    fireEvent.change(field, { target: { value: "zzz" } });
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(state()).toBe("1|");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    vi.useRealTimers();
    expect(state()).toBe("1|zzz");
    expect(await screen.findByRole("heading", { level: 2, name: 'No documents match "zzz"' })).toBeInTheDocument();
    expect(screen.getByText("Check the spelling or try a shorter search.")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search documents" })).toHaveValue("zzz");
    expect(listCalls().at(-1)?.params).toMatchObject({ keywords: "zzz", page: 1 });
    await userEvent.click(within(screen.getByTestId("empty-state")).getByRole("button", { name: "Clear search" }));
    await waitFor(() => expect(state()).toBe("1|"));
    expect(await screen.findByTestId("documents-table")).toBeInTheDocument();
  });

  it("shows an in-place error with Try again that refetches, naming the documents", async () => {
    server.forced[`GET /api/v1/datasets/${DATASET_ID}/documents`] = { status: 503, message: "down" };
    renderTable();
    const failed = await screen.findByTestId("error-state");
    expect(within(failed).getByRole("heading", { name: "Couldn't load documents" })).toBeInTheDocument();
    delete server.forced[`GET /api/v1/datasets/${DATASET_ID}/documents`];
    await userEvent.click(within(failed).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("documents-table")).toBeInTheDocument();
  });
});

describe("Paging (20 per page)", () => {
  beforeEach(() => {
    server.documents[DATASET_ID] = docs(45);
  });

  it("requests 20 at a time and moves with Previous and Next", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    expect(listCalls()[0]?.params).toEqual({ page: 1, page_size: 20 });
    expect(rows()).toHaveLength(20);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(listCalls().at(-1)?.params).toEqual({ page: 3, page_size: 20 });
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(state()).toBe("2|"));
  });

  it("steps back to the last page that exists when the requested page is past the end", async () => {
    renderTable({ initialPage: 9 });
    await waitFor(() => expect(state()).toBe("3|"));
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(screen.queryByText("No documents yet")).toBeNull();
  });
});

describe("Delete icons and the delete dialog (DOC-14, D-09)", () => {
  const MEMBER: SessionUser = { ...OWNER, id: "u4", nickname: "Dan", tenantId: "t4", tenantName: "Dan's workspace", role: "owner" };

  function actAsMember() {
    // Dan is a plain member of Ada's workspace t1 and uploaded only the second document.
    server.memberships = [membershipRow("t4", "Dan's workspace", "owner", "Dan"), membershipRow("t1", "Ada's workspace", "normal", "Ada")];
    server.documents[DATASET_ID] = [documentRow(1, { created_by: "u1" }), documentRow(2, { created_by: "u4" })];
    useUserStore.getState().reset();
    useWorkspaceStore.getState().reset();
    useUserStore.getState().setUser(MEMBER);
    useWorkspaceStore.getState().initialise("u4", "t4", storedMemberships(server.memberships));
    useWorkspaceStore.getState().setActive("t1");
  }

  it("draws a delete icon on every row for the dataset's creator, labelled with the file name", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    const buttons = screen.getAllByTestId("document-delete");
    expect(buttons).toHaveLength(3);
    expect(buttons[0]).toHaveAccessibleName("Delete report-01.pdf");
  });

  it("draws the icon only on the member's own rows and leaves the other cell empty", async () => {
    actAsMember();
    renderTable();
    await screen.findByTestId("documents-table");
    const [first, second] = rows() as [HTMLElement, HTMLElement];
    expect(within(first).queryByTestId("document-delete")).toBeNull();
    expect(within(second).getByTestId("document-delete")).toBeInTheDocument();
    expect(within(first).queryByRole("button")).toBeNull();
  });

  it("opens the named confirmation, deletes the one document and moves focus to the table caption", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rows()[1] as HTMLElement).getByTestId("document-delete"));
    const dialog = await screen.findByTestId("document-delete-dialog");
    expect(within(dialog).getByText('"report-02.pdf" will be removed from Reports. This can\'t be undone.')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("document-delete-confirm"));
    await waitFor(() => expect(rows()).toHaveLength(2));
    const sent = server.callsTo("DELETE", `/api/v1/datasets/${DATASET_ID}/documents`);
    expect(sent).toHaveLength(1);
    expect(JSON.parse(String(sent[0]?.data))).toEqual({ ids: [documentRow(2).id] });
    await waitFor(() => expect(screen.getByText("Documents in Reports")).toHaveFocus());
  });

  it("returns focus to the row's delete icon when the confirmation is dismissed with Keep document", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    const icon = within(rows()[0] as HTMLElement).getByTestId("document-delete");
    await userEvent.click(icon);
    await userEvent.click(await screen.findByTestId("document-delete-keep"));
    await waitFor(() => expect(screen.queryByTestId("document-delete-dialog")).toBeNull());
    await waitFor(() => expect(icon).toHaveFocus());
    expect(rows()).toHaveLength(3);
  });

  it("steps back one page when deleting the only document on the last page", async () => {
    server.documents[DATASET_ID] = docs(21);
    renderTable({ initialPage: 2 });
    await waitFor(() => expect(rows()).toHaveLength(1));
    await userEvent.click(within(rows()[0] as HTMLElement).getByTestId("document-delete"));
    await userEvent.click(await screen.findByTestId("document-delete-confirm"));
    await waitFor(() => expect(state()).toBe("1|"));
    await waitFor(() => expect(rows()).toHaveLength(20));
    expect(screen.queryByText("No documents yet")).toBeNull();
  });

  it("shows the lost-permission alert on a 403 and refetches the table", async () => {
    server.forced[`DELETE /api/v1/datasets/${DATASET_ID}/documents`] = { status: 403, message: "no" };
    renderTable();
    await screen.findByTestId("documents-table");
    const before = listCalls().length;
    await userEvent.click(within(rows()[0] as HTMLElement).getByTestId("document-delete"));
    await userEvent.click(await screen.findByTestId("document-delete-confirm"));
    const alert = await screen.findByTestId("document-delete-error");
    expect(alert).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(before));
  });
});
