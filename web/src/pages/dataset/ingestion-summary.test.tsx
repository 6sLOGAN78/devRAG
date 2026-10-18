import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { waitUntil } from "@/test/wait-until";
import { datasetLogsPath } from "@/constants/app-paths";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { DOCS_URL, renderTable, server, useFilesServer } from "@/test/files-harness";
import { advanceParse, setFileExtra } from "@/test/server-areas/files";
import { IngestionSummary } from "./ingestion-summary";

useFilesServer();

const SUMMARY_URL = `/api/v1/datasets/${DATASET_ID}/ingestions/summary`;

function renderSummary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <IngestionSummary datasetId={DATASET_ID} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("IngestionSummary (KB-14)", () => {
  it("shows the eight values in order, zeros included, and the Parsing log link built with the path helper", async () => {
    renderSummary();
    const card = await screen.findByTestId("ingestion-summary");
    await waitFor(() => expect(within(card).getByTestId("summary-count-unstart")).toHaveTextContent("3"));
    const labels = Array.from(card.querySelectorAll("dt")).map((dt) => dt.textContent);
    expect(labels).toEqual(["Not started", "Parsing", "Finished", "Failed", "Cancelled", "Partly indexed", "Chunks", "Tokens"]);
    for (const id of ["running", "done", "failed", "cancelled", "partial", "chunk-total", "token-total"]) expect(within(card).getByTestId(`summary-count-${id}`)).toHaveTextContent("0");
    expect(within(card).getByRole("heading", { name: "Parsing" })).toBeInTheDocument();
    expect(within(card).getByTestId("ingestion-log-link")).toHaveAttribute("href", datasetLogsPath(DATASET_ID));
    expect(within(card).getByTestId("ingestion-log-link")).toHaveTextContent("Parsing log");
  });

  it("shows the title, the link and eight skeleton values while loading", async () => {
    server.holds[`GET ${SUMMARY_URL}`] = new Promise<void>(() => {});
    renderSummary();
    const card = await screen.findByTestId("ingestion-summary");
    expect(within(card).getAllByTestId("summary-skeleton")).toHaveLength(8);
    expect(within(card).getByTestId("ingestion-log-link")).toBeInTheDocument();
  });

  it("counts failed and cancelled documents that kept chunks as partly indexed too, and labels the token total as a pair", async () => {
    server.documents[DATASET_ID] = [
      documentRow(1, { run: "3", chunk_num: 4 }),
      documentRow(2, { run: "4", chunk_num: 2 }),
      documentRow(3, { run: "2" }),
      documentRow(4, { run: "1" }),
    ];
    setFileExtra(server, documentRow(1).id, { tokenNum: 1200 });
    renderSummary();
    await waitFor(() => expect(screen.getByTestId("summary-count-done")).toHaveTextContent("1"));
    expect(screen.getByTestId("summary-count-failed")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-count-cancelled")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-count-partial")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-count-running")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-count-chunk-total")).toHaveTextContent("6");
    expect(screen.getByTestId("summary-count-token-total")).toHaveTextContent("1,200");
    expect(screen.queryByText(/tokens$/)).toBeNull();
  });

  it("shows its own error line with Try again", async () => {
    server.forced[`GET ${SUMMARY_URL}`] = { status: 500, message: "x" };
    renderSummary();
    expect(await screen.findByTestId("ingestion-summary-error")).toHaveTextContent("Couldn't load the parsing summary.");
    delete server.forced[`GET ${SUMMARY_URL}`];
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("summary-count-unstart")).toHaveTextContent("3"));
    expect(screen.queryByTestId("ingestion-summary-error")).toBeNull();
  });

  it("polls every 2 seconds while something runs", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.1 })];
    renderSummary();
    await waitFor(() => expect(screen.getByTestId("summary-count-running")).toHaveTextContent("1"));
    act(() => advanceParse(server, documentRow(1).id, { run: "3", progress: 1, chunkCount: 8 }));
    await waitFor(() => expect(screen.getByTestId("summary-count-done")).toHaveTextContent("1"), { timeout: 5000 });
    expect(screen.getByTestId("summary-count-chunk-total")).toHaveTextContent("8");
    const calls = server.callsTo("GET", SUMMARY_URL).length;
    // Nothing runs any more, so no further summary request may arrive within one poll period (2 s) plus margin.
    await expect(
      waitUntil(() => server.callsTo("GET", SUMMARY_URL).length > calls, { timeout: 2600, describe: "another summary poll" }),
    ).rejects.toThrow(/timed out/);
    expect(server.callsTo("GET", SUMMARY_URL).length).toBe(calls);
  }, 15000);
});

describe("The summary inside the table", () => {
  it("is not rendered for an empty dataset", async () => {
    server.documents[DATASET_ID] = [];
    renderTable();
    await screen.findByRole("heading", { level: 2, name: "No documents yet" });
    expect(screen.queryByTestId("ingestion-summary")).toBeNull();
  });

  it("fails alone: the table stays when the summary cannot be loaded", async () => {
    server.forced[`GET ${SUMMARY_URL}`] = { status: 500, message: "x" };
    renderTable();
    expect(await screen.findByTestId("documents-table")).toBeInTheDocument();
    expect(await screen.findByTestId("ingestion-summary-error")).toBeInTheDocument();
    expect(server.callsTo("GET", DOCS_URL).length).toBeGreaterThan(0);
  });
});
