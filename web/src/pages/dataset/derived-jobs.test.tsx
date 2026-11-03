import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { AxiosHeaders } from "axios";
import { expect, it, vi } from "vitest";
import type { DatasetDetailView } from "@/services/dataset-service";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DATASET, OWNER, server, useFilesServer } from "@/test/files-harness";
import { DATASET_ID, membershipRow, storedMemberships } from "@/test/dataset-server";
import { DerivedJobs } from "./derived-jobs";

useFilesServer();
const URL = `/api/v1/datasets/${DATASET_ID}/jobs`;
const JOB_ID = "abcdef0123456789abcdef0123456789";
const ARTIFACT_ID = "1234567890abcdef1234567890abcdef";
const HISTORY = `/api/v1/datasets/${DATASET_ID}/artifacts/alteration`;
const detail = { ...DATASET, permission: "team", parserConfig: { chunkTokenNum: 512, delimiter: "\n", overlappedPercent: 0 },
  description: "", avatar: "", embdId: "embed", embeddingDimension: 8, docNum: 1, chunkNum: 1, tokenNum: 10,
  language: "English", parserId: "naive", createTime: 1, updateTime: 1, uploadLimits: null } as DatasetDetailView;

server.use(({ server: state, method, url, config, ok }) => {
  if (method === "PUT" && url === `/api/v1/datasets/${DATASET_ID}`) {
    expect(JSON.parse(String(config.data))).toEqual({ parser_config: { raptor: true } });
    return ok({ ...DATASET, parser_config: { raptor: true } });
  }
  if (method === "GET" && url === HISTORY) {
    const rows = state.areaState<Array<Record<string, unknown>>>("alterations", () => []);
    return ok({ items: rows, total: rows.length, page: 1, size: 20 });
  }
  if (method === "DELETE" && url === `/api/v1/datasets/${DATASET_ID}/raptor`) {
    const jobs = state.areaState<Array<Record<string, unknown>>>("jobs", () => []);
    for (const job of jobs) if (job.type === "raptor") { job.run = "2"; job.artifact_filename = null; }
    state.areaState<Array<Record<string, unknown>>>("alterations", () => []).unshift({ actor: OWNER.id, type: "raptor", generation: JOB_ID, outcome: "done", time: 1, deleted_count: 4 });
    return ok({ type: "raptor", deleted_count: 4, artifact_count: 1 });
  }
  if (method === "GET" && url === `/api/v1/documents/artifact/${ARTIFACT_ID}.json`) {
    return { data: new Blob(['{"schema_version":1}'], { type: "application/json" }), status: 200,
      statusText: "OK", headers: new AxiosHeaders(), config } as never;
  }
  if (!url.startsWith(URL)) return undefined;
  const jobs = state.areaState<Array<Record<string, unknown>>>("jobs", () => []);
  if (method === "GET" && url === URL) return ok({ items: jobs });
  if (method === "POST" && url === URL) {
    const type = JSON.parse(String(config.data)).type;
    expect(["enrich", "raptor"]).toContain(type);
    const job = { id: JOB_ID, type, run: "1", total: 2, completed: 0, failed: 0, progress: 0, created_at: 1, updated_at: 1 };
    jobs.unshift(job);
    return ok(job);
  }
  if (method === "POST" && url === `${URL}/${JOB_ID}/cancel`) {
    jobs[0] = { ...jobs[0], run: "2" };
    return ok(jobs[0]);
  }
  return undefined;
});

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<MemoryRouter><QueryClientProvider client={client}><DerivedJobs dataset={detail} /></QueryClientProvider></MemoryRouter>);
  return { ...view, client };
}

it("starts a scoped enrichment run and shows progress, then cancels it", async () => {
  mount();
  const user = userEvent.setup();
  expect(server.callsTo("GET", URL)).toHaveLength(0);
  await user.click(screen.getByTestId("dataset-jobs-open"));
  expect(await screen.findByText("No jobs yet.")).toBeInTheDocument();
  await user.click(screen.getByTestId("dataset-jobs-start"));
  await waitFor(() => expect(server.callsTo("POST", URL)).toHaveLength(1));
  expect(await screen.findByTestId("dataset-job-progress")).toHaveTextContent("0 of 2 documents complete");
  await user.click(within(screen.getByTestId("dataset-job-row")).getByRole("button", { name: "Cancel job" }));
  expect(await screen.findByText("Cancel enrichment refresh?")).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Cancel job" }).at(-1)!);
  await waitFor(() => expect(server.callsTo("POST", `${URL}/${JOB_ID}/cancel`)).toHaveLength(1));
  expect(await screen.findByTestId("dataset-job-progress")).toHaveTextContent("Cancelled");
});

it("hides held old workspace jobs after the active workspace changes", async () => {
  server.memberships.push(membershipRow("t2", "Another workspace", "normal"));
  act(() => useWorkspaceStore.getState().initialise(OWNER.id, "t1", storedMemberships(server.memberships)));
  let release: () => void = () => {};
  server.holds[`GET ${URL}`] = new Promise<void>(resolve => { release = resolve; });
  mount();
  const user = userEvent.setup();
  await user.click(screen.getByTestId("dataset-jobs-open"));
  act(() => useWorkspaceStore.getState().setActive("t2"));
  act(() => release());
  await waitFor(() => expect(screen.queryByTestId("dataset-derived-jobs")).toBeNull());
  expect(screen.queryByText("Enrichment refresh")).toBeNull();
});

it("enables RAPTOR and starts a source-linked summary run", async () => {
  mount();
  const user = userEvent.setup();
  await user.click(screen.getByTestId("dataset-jobs-open"));
  await user.click(screen.getByTestId("dataset-raptor-start"));
  await waitFor(() => expect(server.callsTo("PUT", `/api/v1/datasets/${DATASET_ID}`)).toHaveLength(1));
  await waitFor(() => expect(server.callsTo("POST", URL)).toHaveLength(1));
  expect(await screen.findByText("RAPTOR summaries")).toBeInTheDocument();
});

it("downloads an owned artifact and confirms derived-only deletion with bounded history", async () => {
  server.areaState<Array<Record<string, unknown>>>("jobs", () => []).push({
    id: JOB_ID, type: "raptor", run: "3", total: 1, completed: 1, failed: 0, progress: 1,
    created_at: 1, updated_at: 1, artifact_filename: `${ARTIFACT_ID}.json`,
  });
  const create = vi.spyOn(globalThis.URL, "createObjectURL").mockReturnValue("blob:raptor-test");
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    mount();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("dataset-jobs-open"));
    await user.click(await screen.findByTestId("dataset-job-artifact"));
    await waitFor(() => expect(server.callsTo("GET", `/api/v1/documents/artifact/${ARTIFACT_ID}.json`)).toHaveLength(1));
    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    await user.click(screen.getByTestId("dataset-raptor-delete"));
    expect(await screen.findByText("Delete RAPTOR summaries?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep summaries" }));
    expect(server.callsTo("DELETE", `/api/v1/datasets/${DATASET_ID}/raptor`)).toHaveLength(0);
    await user.click(screen.getByTestId("dataset-raptor-delete"));
    await user.click(screen.getAllByRole("button", { name: "Delete summaries" }).at(-1)!);
    await waitFor(() => expect(server.callsTo("DELETE", `/api/v1/datasets/${DATASET_ID}/raptor`)).toHaveLength(1));
    expect(await screen.findByTestId("dataset-raptor-deleted")).toHaveTextContent("Deleted 4 summaries and 1 generated artifacts.");
    await user.click(screen.getByTestId("dataset-alteration-open"));
    expect(await screen.findByTestId("dataset-alteration-row")).toHaveTextContent("4 summaries removed");
  } finally { create.mockRestore(); click.mockRestore(); }
});
