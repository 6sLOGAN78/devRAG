import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, RouterProvider, createMemoryRouter, matchPath } from "react-router";
import { describe, expect, it } from "vitest";
import { CHUNK_ROUTE, chunkPath, datasetLogsPath, documentViewerPath } from "@/constants/app-paths";
import { routes } from "@/constants/routes";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { DATASET, server, useFilesServer } from "@/test/files-harness";
import ChunkInspector from "@/pages/chunk";
import { DatasetFiles } from "./dataset-files";
import { IngestionSummary } from "./ingestion-summary";

useFilesServer();

const DOC = "d".repeat(31) + "1";

/** True when the pathname of a link is the path of an entry of the route table (other than the catch-all). */
function registered(href: string): boolean {
  const pathname = new URL(href, "http://app.test").pathname;
  return routes.some((route) => route.path !== "*" && matchPath(route.path, pathname) !== null);
}

function client(): QueryClient {
  const created = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(created);
  return created;
}

describe("every link that leaves the document table, the summary and the inspector reaches a registered route", () => {
  it("document row: name link, 'View chunks' and 'Open document'", async () => {
    const row = documentRow(1, { id: DOC, run: "3", chunk_num: 2 });
    server.documents[DATASET_ID] = [row];
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QueryClientProvider client={client()}>
          <DatasetFiles dataset={DATASET} limits={null} page={1} keywords="" onPageChange={() => {}} onSearch={() => {}} onUpload={() => {}} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const name = await screen.findByTestId("document-name-link");
    expect(name).toHaveAttribute("href", chunkPath(DATASET_ID, DOC));
    expect(registered(name.getAttribute("href") ?? "")).toBe(true);

    await user.click(screen.getByTestId("document-more"));
    const menu = await screen.findByTestId("document-menu");
    const chunks = within(menu).getByRole("menuitem", { name: "View chunks" });
    const open = within(menu).getByRole("menuitem", { name: "Open document" });
    expect(chunks.getAttribute("href")).toBe(chunkPath(DATASET_ID, DOC));
    expect(open.getAttribute("href")).toBe(documentViewerPath(DATASET_ID, DOC));
    for (const link of [chunks, open]) expect(registered(link.getAttribute("href") ?? "")).toBe(true);
  });

  it("ingestion summary: 'Parsing log'", async () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={client()}>
          <IngestionSummary datasetId={DATASET_ID} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const link = await screen.findByTestId("ingestion-log-link");
    expect(link.getAttribute("href")).toBe(datasetLogsPath(DATASET_ID));
    expect(registered(link.getAttribute("href") ?? "")).toBe(true);
  });

  it("chunk inspector meta line: 'Open document'", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { id: DOC, run: "3", chunk_num: 0 })];
    const router = createMemoryRouter([{ path: CHUNK_ROUTE, element: <ChunkInspector /> }], { initialEntries: [chunkPath(DATASET_ID, DOC)] });
    render(
      <QueryClientProvider client={client()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    const link = await screen.findByTestId("chunk-open-document");
    expect(link.getAttribute("href")).toBe(documentViewerPath(DATASET_ID, DOC));
    expect(registered(link.getAttribute("href") ?? "")).toBe(true);
  });
});
