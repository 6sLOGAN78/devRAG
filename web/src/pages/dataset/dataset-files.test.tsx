import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { chunkPath, documentViewerPath } from "@/constants/app-paths";
import { ApiError, http, registerQueryClient } from "@/services/http";
import { toDocument, type DocumentView } from "@/services/document-service";
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
import { setFileExtra } from "@/test/server-areas/files";
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
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Harness {...props} />
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>,
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
  it("is a table with a screen-reader caption, scoped column headers and one row per document", async () => {
    renderTable();
    const table = await screen.findByTestId("documents-table");
    expect(table.tagName).toBe("TABLE");
    expect(within(table).getByText("Documents in Reports").tagName).toBe("CAPTION");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["Select", "Name", "Size", "Uploaded", "Status", "Progress", "In search", "Actions"]);
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

  it("shows 'Unknown status' as an outline badge for a run value the table does not know, and no Parse control for it", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "DONE" })];
    renderTable();
    await screen.findByTestId("documents-table");
    expect(screen.getAllByTestId("document-status").map((s) => s.textContent)).toEqual(["Unknown status"]);
    expect(screen.queryByTestId("document-parse")).toBeNull();
    expect(screen.queryByTestId("document-cancel")).toBeNull();
    expect(screen.queryByTestId("document-reparse")).toBeNull();
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

const view = (over: Partial<DocumentView> = {}): DocumentView => toDocument({ ...documentRow(1), ...over });

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
    expect(within(first).queryByTestId("document-parse")).toBeNull();
    expect(within(first).queryByTestId("document-search-switch")).toBeNull();
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

describe("DocumentStatusBadge status map (D-07, D-13, D-14)", () => {
  const error = { step: "chunk", code: "no_readable_text", message: "" };
  const cases: Array<[string, Partial<DocumentView> & Record<string, unknown>, string, string[]]> = [
    ["not started", { run: "0" }, "Not started", []],
    ["not started, with chunks left from before (R-163)", { run: "0", chunk_count: 4 }, "Not started", ["4 chunks"]],
    ["not parseable", { run: "0", parseable: false }, "Parsing not available yet", []],
    ["parsing", { run: "1" }, "Parsing", []],
    ["finished", { run: "3", chunk_count: 1 }, "Finished", ["1 chunk"]],
    ["finished with skipped pages", { run: "3", chunk_count: 7, pages_total: 13, pages_without_text: 2 }, "Finished", ["7 chunks", "2 of 13 pages had no readable text"]],
    ["failed", { run: "4", error }, "Failed", ["This PDF has no readable text; scanned documents are not supported yet."]],
    ["cancelled", { run: "2" }, "Cancelled", []],
    ["failed with chunks left", { run: "4", chunk_count: 3, error }, "Partly indexed", ["3 chunks searchable. Parsing failed: This PDF has no readable text; scanned documents are not supported yet."]],
    ["cancelled with chunks left", { run: "2", chunk_count: 2 }, "Partly indexed", ["2 chunks searchable. Parsing was cancelled."]],
    ["unknown", { run: "7" }, "Unknown status", []],
    ["empty", { run: "" }, "Unknown status", []],
  ];
  it.each(cases)("%s", (_name, over, text, details) => {
    render(<DocumentStatusBadge document={view(over as never)} />);
    expect(screen.getByTestId("document-status")).toHaveTextContent(text);
    expect(screen.queryAllByTestId("document-status-detail").map((d) => d.textContent)).toEqual(details);
  });

  it("shows the server's plain message for an unknown failure code, as text", () => {
    render(<DocumentStatusBadge document={view({ run: "4", error: { step: "x", code: "weird", message: "<b>odd</b> thing" } } as never)} />);
    expect(screen.getByTestId("document-status-detail")).toHaveTextContent("<b>odd</b> thing");
    expect(document.querySelector("b")).toBeNull();
  });

  it("gives every state an icon, except the unknown one", () => {
    for (const run of ["0", "1", "2", "3", "4"]) {
      const { unmount } = render(<DocumentStatusBadge document={view({ run } as never)} />);
      expect(screen.getByTestId("document-status").querySelector("svg")).not.toBeNull();
      unmount();
    }
  });

  it("stops the spinner under reduced motion", () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} })) as never;
    try {
      render(<DocumentStatusBadge document={view({ run: "1" } as never)} />);
      expect(screen.getByTestId("document-status").querySelector("svg")?.getAttribute("class") ?? "").not.toContain("animate-spin");
    } finally {
      window.matchMedia = original;
    }
    cleanup();
    render(<DocumentStatusBadge document={view({ run: "1" } as never)} />);
    expect(screen.getByTestId("document-status").querySelector("svg")?.getAttribute("class") ?? "").toContain("animate-spin");
  });
});

describe("Progress cell (FE-18)", () => {
  const cell = async (over: Record<string, unknown>) => {
    server.documents[DATASET_ID] = [documentRow(1, over as never)];
    renderTable();
    await screen.findByTestId("documents-table");
    return screen.getByTestId("document-progress");
  };

  it("floors a running 0.996 to 99, never 100", async () => {
    const progress = await cell({ run: "1", progress: 0.996 });
    expect(progress).toHaveTextContent("99%");
    expect(progress).not.toHaveTextContent("100%");
    expect(within(progress).getByRole("progressbar", { name: "Parsing progress for report-01.pdf" })).toHaveAttribute("aria-valuenow", "99");
  });

  it("shows the latest server progress line, or 'Waiting for a worker', with the full text in title", async () => {
    const first = await cell({ run: "1", progress: 0.3 });
    expect(within(first).getByTestId("document-progress-message")).toHaveTextContent("Waiting for a worker");
    cleanup();
    setFileExtra(server, documentRow(1).id, { progressMessage: "Embedding chunk 4 of 9 <i>x</i>" });
    renderTable();
    const message = await screen.findByText("Embedding chunk 4 of 9 <i>x</i>");
    expect(message).toHaveAttribute("title", "Embedding chunk 4 of 9 <i>x</i>");
    expect(message.className).toContain("truncate");
    expect(message.querySelector("i")).toBeNull();
  });

  it("shows 100% when finished, the percentage reached when cancelled, an em dash when failed", async () => {
    expect(await cell({ run: "3", progress: 1, chunk_num: 2 })).toHaveTextContent("100%");
    cleanup();
    const cancelled = await cell({ run: "2", progress: 0.42 });
    expect(cancelled).toHaveTextContent("42%");
    expect(within(cancelled).queryByRole("progressbar")).toBeNull();
    cleanup();
    const failed = await cell({ run: "4", progress: 0.5 });
    expect(failed).toHaveTextContent("—");
    expect(failed).toHaveTextContent("No progress");
  });
});

describe("Document row (UI-15)", () => {
  it("carries data-run and data-doc-id, links the name to the chunk screen and dims a document switched off", async () => {
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2)];
    setFileExtra(server, documentRow(2).id, { enabled: false });
    renderTable();
    await screen.findByTestId("documents-table");
    const [first, second] = rows() as [HTMLElement, HTMLElement];
    expect(first).toHaveAttribute("data-run", "0");
    expect(first).toHaveAttribute("data-doc-id", documentRow(1).id);
    const link = within(first).getByTestId("document-name-link");
    expect(link).toHaveAttribute("href", chunkPath(DATASET_ID, documentRow(1).id));
    expect(link.className).toContain("break-all");
    expect(link.className).toContain("line-clamp-2");
    expect(link).toHaveAttribute("title", "report-01.pdf");
    expect(within(second).getByTestId("document-name-link").className).toContain("text-muted-foreground");
  });

  it("builds the menu links with the path builders", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rows()[0] as HTMLElement).getByRole("button", { name: "More actions for report-01.pdf" }));
    const id = documentRow(1).id;
    expect(await screen.findByTestId("document-menu-chunks")).toHaveAttribute("href", chunkPath(DATASET_ID, id));
    expect(screen.getByTestId("document-menu-open")).toHaveAttribute("href", documentViewerPath(DATASET_ID, id));
    expect(screen.queryByTestId("document-menu-details")).toBeNull();
  });

  it("shows a thumbnail only from the validated field and falls back to the icon when it cannot be decoded", async () => {
    const png = "data:image/png;base64,iVBORw0KGgo=";
    setFileExtra(server, documentRow(1).id, { thumbnail: png });
    setFileExtra(server, documentRow(2).id, { thumbnail: "https://evil.test/x.png" });
    renderTable();
    await screen.findByTestId("documents-table");
    const thumbnails = screen.getAllByTestId("document-thumbnail");
    expect(thumbnails).toHaveLength(1);
    expect(thumbnails[0]).toHaveAttribute("src", png);
    expect(thumbnails[0]).toHaveAttribute("alt", "");
    expect(thumbnails[0]).toHaveAttribute("loading", "lazy");
    fireEvent.error(thumbnails[0] as HTMLElement);
    expect(screen.queryByTestId("document-thumbnail")).toBeNull();
  });

  it("renders a hostile name as text everywhere it appears", async () => {
    const hostile = "<img src=x onerror=alert(1)>.pdf";
    server.documents[DATASET_ID] = [documentRow(1, { name: hostile })];
    renderTable();
    const table = await screen.findByTestId("documents-table");
    expect(table.querySelector("img, script")).toBeNull();
    expect(within(table).getByRole("checkbox", { name: `Select ${hostile}` })).toBeInTheDocument();
    expect(within(table).getByRole("button", { name: `Parse ${hostile}` })).toBeInTheDocument();
  });

  it("draws the select column only when a row qualifies, and the 'In search' cell as text for a caller who may not change", async () => {
    const MEMBER: SessionUser = { ...OWNER, id: "u4", tenantId: "t4", tenantName: "Dan's workspace" };
    server.memberships = [membershipRow("t4", "Dan's workspace", "owner", "Dan"), membershipRow("t1", "Ada's workspace", "normal", "Ada")];
    server.documents[DATASET_ID] = [documentRow(1, { created_by: "u1" })];
    useUserStore.getState().reset();
    useWorkspaceStore.getState().reset();
    useUserStore.getState().setUser(MEMBER);
    useWorkspaceStore.getState().initialise("u4", "t4", storedMemberships(server.memberships));
    useWorkspaceStore.getState().setActive("t1");
    renderTable();
    await screen.findByTestId("documents-table");
    expect(screen.queryByTestId("documents-select-all")).toBeNull();
    expect(screen.queryByTestId("document-select")).toBeNull();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Name", "Size", "Uploaded", "Status", "Progress", "In search", "Actions"]);
    expect(screen.getByTestId("document-search-text")).toHaveTextContent("On");
    expect(screen.queryByTestId("document-search-switch")).toBeNull();
    expect(screen.queryByTestId("document-parse")).toBeNull();
    expect(screen.getByRole("button", { name: "More actions for report-01.pdf" })).toBeInTheDocument();
  });
});
