import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { datasetFilesPath, datasetLogsPath } from "@/constants/app-paths";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DATASET_ID, OTHER_DATASET_ID, createDatasetServer, datasetRow, documentRow, membershipRow, storedMemberships } from "@/test/dataset-server";
import { addFileLog } from "@/test/server-areas/files";
import { setLogExtra, type LogExtra } from "@/test/server-areas/ingestion-logs";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";
import ParsingLogPage from ".";

// The real page, hooks, services and HTTP client against the in-memory server and its ingestion-logs area.
const ADA: SessionUser = {
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
let router: ReturnType<typeof createMemoryRouter>;

const LOGS_URL = `/api/v1/datasets/${DATASET_ID}/ingestions`;
const logCalls = () => server.callsTo("GET", LOGS_URL);
const idOf = (n: number) => `log${String(n).padStart(29, "0")}`;
const location = () => `${router.state.location.pathname}${router.state.location.search}`;
const rows = () => screen.queryAllByTestId("log-row");

function renderPage(entry = datasetLogsPath(DATASET_ID)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  router = createMemoryRouter(
    [
      { path: "/dataset/logs", element: <ParsingLogPage /> },
      { path: "/dataset/files", element: <p data-testid="files-page">files</p> },
      { path: "/datasets", element: <p data-testid="gallery-page">gallery</p> },
    ],
    { initialEntries: [entry] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function signIn(rowsOf = [membershipRow("t1", "Ada's workspace", "owner", "Ada")]) {
  server.memberships = rowsOf;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(ADA);
  useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(rowsOf));
}

/** Adds the run `n` (oldest is 1) of document `doc`. */
function run(n: number, doc: number, result: "running" | "done" | "failed" | "cancelled", extra: LogExtra = {}): string {
  addFileLog(server, { id: idOf(n), docId: documentRow(doc).id, result });
  setLogExtra(server, idOf(n), extra);
  return idOf(n);
}

beforeEach(() => {
  server.reset();
  server.datasets[DATASET_ID] = datasetRow();
  server.documents[DATASET_ID] = [documentRow(1), documentRow(2), documentRow(3)];
  signIn();
  setAuthorization("tok-session");
  http.defaults.adapter = server.adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Structure and rows (KB-15)", () => {
  it("shows the back link, header, helper line, caption, columns and runs newest first", async () => {
    run(1, 1, "done", { durationSeconds: 12.4 });
    run(2, 2, "failed", { error: { step: "embed", code: "provider_timeout", message: "x" }, attempts: 3 });
    run(3, 3, "cancelled");
    renderPage();
    const page = await screen.findByTestId("logs-page");
    const back = within(page).getByTestId("logs-back");
    expect(back).toHaveAttribute("href", datasetFilesPath(DATASET_ID));
    expect(back).toHaveTextContent("Reports");
    expect(within(page).getByRole("heading", { level: 1, name: "Parsing log" })).toBeInTheDocument();
    expect(within(page).getByText("Every parsing run in Reports, newest first.")).toBeInTheDocument();
    await waitFor(() => expect(rows()).toHaveLength(3));
    const table = within(page).getByTestId("logs-table");
    expect(table.querySelector("caption")).toHaveTextContent("Parsing runs in Reports");
    expect(table.querySelector("caption")?.className).toContain("sr-only");
    expect(Array.from(table.querySelectorAll("th")).map((th) => th.textContent)).toEqual(["Document", "Started", "Duration", "Result", "Attempts", "Actions"]);
    expect(rows().map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual(["report-03.pdf", "report-02.pdf", "report-01.pdf"]);
    expect(document.title).toBe("Parsing log for Reports - devRag");
  });

  it("shows the result as an icon and a word, the short reason under a failure, attempts and duration", async () => {
    run(1, 1, "done", { durationSeconds: 12.4 });
    run(2, 2, "failed", { error: { step: "embed", code: "provider_timeout", message: "x" }, attempts: 3, durationSeconds: 3.2 });
    run(3, 3, "running");
    run(4, 3, "cancelled");
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(4));
    const [cancelled, running, failed, done] = rows() as [HTMLElement, HTMLElement, HTMLElement, HTMLElement];
    expect(within(done).getByTestId("log-result")).toHaveTextContent("Finished");
    expect(within(done).getByTestId("log-result").querySelector("svg")).not.toBeNull();
    expect(within(failed).getByTestId("log-result")).toHaveTextContent("Failed");
    expect(failed).toHaveTextContent("The embedding provider timed out.");
    expect(within(running).getByTestId("log-result")).toHaveTextContent("Parsing");
    expect(within(cancelled).getByTestId("log-result")).toHaveTextContent("Cancelled");
    expect(within(done).getAllByRole("cell")[2]).toHaveTextContent("12 s");
    expect(within(failed).getAllByRole("cell")[2]).toHaveTextContent("3.2 s");
    expect(within(failed).getAllByRole("cell")[4]).toHaveTextContent("3 of 3");
    expect(within(done).getAllByRole("cell")[4]).toHaveTextContent("1 of 3");
  });

  it("renders a hostile file name as text", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { name: "<img src=x onerror=alert(1)>.pdf" })];
    run(1, 1, "done");
    const { container } = renderPage();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0]).toHaveTextContent("<img src=x onerror=alert(1)>.pdf");
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens the details sheet of a run from its Details button and returns focus to it", async () => {
    run(1, 1, "failed", { error: { step: "embed", code: "provider_timeout", message: "x" }, lines: ["Embedding batch 1"] });
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(1));
    const button = within(rows()[0] as HTMLElement).getByRole("button", { name: "Parsing details for report-01.pdf" });
    expect(button).toHaveTextContent("Details");
    await userEvent.click(button);
    const sheet = await screen.findByTestId("parsing-details");
    expect(await within(sheet).findByTestId("details-reason")).toHaveTextContent("The embedding provider timed out.");
    expect(within(sheet).getByTestId("details-log")).toHaveTextContent("Embedding batch 1");
    expect(within(sheet).queryByTestId("details-reparse")).toBeNull();
    await userEvent.click(within(sheet).getByTestId("details-close"));
    await waitFor(() => expect(screen.queryByTestId("parsing-details")).toBeNull());
    await waitFor(() => expect(button).toHaveFocus());
  });
});

describe("Paging (FE-01, FE-07)", () => {
  function seedMany(count: number) {
    server.documents[DATASET_ID] = Array.from({ length: count }, (_, i) => documentRow(i + 1));
    for (let n = 1; n <= count; n += 1) run(n, n, "done");
  }

  it("lists 20 a page, names the pagination and steps through the pages with the URL", async () => {
    seedMany(25);
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(20));
    expect(logCalls()[0]?.params).toMatchObject({ page: 1, size: 20 });
    const nav = screen.getByRole("navigation", { name: "Parsing log pages" });
    await userEvent.click(within(nav).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(location()).toBe(`${datasetLogsPath(DATASET_ID)}&page=2`);
    expect(screen.getByRole("navigation", { name: "Parsing log pages" })).toHaveTextContent("Page 2 of 2");
  });

  it("keeps the previous page and the pagination on screen while the next page loads", async () => {
    seedMany(25);
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(20));
    let release: () => void = () => {};
    server.holds[`GET ${LOGS_URL}`] = new Promise<void>((resolve) => (release = resolve));
    const next = within(screen.getByRole("navigation", { name: "Parsing log pages" })).getByRole("button", { name: "Next" });
    await userEvent.click(next);
    await waitUntil(() => logCalls().length === 2, { describe: "the second page request" });
    expect(rows()).toHaveLength(20);
    expect(screen.getByRole("navigation", { name: "Parsing log pages" })).toBeInTheDocument();
    expect(next).toBeInTheDocument();
    release();
    await waitFor(() => expect(rows()).toHaveLength(5));
  });

  it("steps back to the last page, with replace, when the page is beyond the last", async () => {
    seedMany(25);
    renderPage(`${datasetLogsPath(DATASET_ID)}&page=9`);
    await waitFor(() => expect(location()).toBe(`${datasetLogsPath(DATASET_ID)}&page=2`));
    expect(router.state.historyAction).toBe("REPLACE");
    await waitFor(() => expect(rows()).toHaveLength(5));
  });

  it("ignores a malformed page", async () => {
    seedMany(3);
    renderPage(`${datasetLogsPath(DATASET_ID)}&page=abc`);
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(logCalls()[0]?.params).toMatchObject({ page: 1 });
  });
});

describe("States", () => {
  it("shows the header at once and a table skeleton of a header row and five rows while loading", async () => {
    server.holds[`GET ${LOGS_URL}`] = new Promise<void>(() => {});
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Parsing log" })).toBeInTheDocument();
    const skeleton = await screen.findByTestId("logs-skeleton");
    expect(within(skeleton).getAllByTestId("log-row-skeleton")).toHaveLength(5);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the parsing log");
  });

  it("shows the empty state with a link back to the documents", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { level: 2, name: "No parsing runs yet" })).toBeInTheDocument();
    expect(screen.getByText("Each time a document is parsed, the run is listed here with its result.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to documents" })).toHaveAttribute("href", datasetFilesPath(DATASET_ID));
    expect(screen.queryByTestId("logs-table")).toBeNull();
  });

  it("shows an in-place error with Try again", async () => {
    run(1, 1, "done");
    server.forced[`GET ${LOGS_URL}`] = { status: 500, message: "boom" };
    renderPage();
    const error = await screen.findByTestId("error-state");
    expect(error).toHaveTextContent("Couldn't load the parsing log");
    expect(screen.getByRole("heading", { level: 1, name: "Parsing log" })).toBeInTheDocument();
    delete server.forced[`GET ${LOGS_URL}`];
    await userEvent.click(within(error).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
  });

  it("shows 'Dataset not found' for a malformed id and sends no request", async () => {
    renderPage("/dataset/logs?id=nope");
    expect(await screen.findByTestId("dataset-not-found")).toBeInTheDocument();
    expect(server.calls).toHaveLength(0);
  });

  it("shows 'Dataset not found' for a dataset the caller cannot see and asks for no logs", async () => {
    renderPage(datasetLogsPath(OTHER_DATASET_ID));
    expect(await screen.findByTestId("dataset-not-found")).toBeInTheDocument();
    expect(server.calls.filter((c) => String(c.url).includes("/ingestions"))).toHaveLength(0);
  });
});

describe("Live and binding (FE-02)", () => {
  it("polls while a run is going and stops when none runs", async () => {
    run(1, 1, "running");
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(within(rows()[0] as HTMLElement).getByTestId("log-result")).toHaveTextContent("Parsing");
    const files = server.areaState<{ logs: { id: string; result: string }[] }>("files", () => ({ logs: [] }));
    (files.logs[0] as { result: string }).result = "done";
    await waitUntil(() => within(rows()[0] as HTMLElement).getByTestId("log-result").textContent === "Finished", { timeout: 6000, describe: "the polled result" });
    const settled = logCalls().length;
    await expect(waitUntil(() => logCalls().length > settled, { timeout: 2600 })).rejects.toThrow(/timed out/);
  }, 20_000);

  it("sends exactly one logs request, for the dataset's workspace and the page in the address, on a deep link into a joined workspace", async () => {
    signIn([membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")]);
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t9", created_by: "u1" });
    const tenants: (string | null)[] = [];
    server.use(({ url, method }) => {
      if (method === "GET" && url === LOGS_URL) tenants.push(useWorkspaceStore.getState().activeTenantId);
      return undefined;
    });
    for (let n = 1; n <= 25; n += 1) {
      server.documents[DATASET_ID] = [...(server.documents[DATASET_ID] ?? []), documentRow(n + 10)];
      run(n, n + 10, "done");
    }
    renderPage(`${datasetLogsPath(DATASET_ID)}&page=2`);
    await waitFor(() => expect(rows()).toHaveLength(5));
    await waitFor(() => expect(useWorkspaceStore.getState().activeTenantId).toBe("t9"));
    expect(logCalls()).toHaveLength(1);
    expect(logCalls()[0]?.params).toMatchObject({ page: 2, size: 20 });
    expect(tenants).toEqual(["t9"]);
    expect(location()).toBe(`${datasetLogsPath(DATASET_ID)}&page=2`);
  });

  it("goes to /datasets when the user switches workspace", async () => {
    signIn([membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")]);
    run(1, 1, "done");
    renderPage();
    await waitFor(() => expect(rows()).toHaveLength(1));
    useWorkspaceStore.getState().setActive("t9");
    expect(await screen.findByTestId("gallery-page")).toBeInTheDocument();
    expect(router.state.historyAction).toBe("REPLACE");
  });
});
