import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "i18next";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { FAILURE_CODES, STEPS, failureReasonKey, failureStepKey } from "@/constants/failure-codes";
import { registerQueryClient } from "@/services/http";
import type { IngestionLogDetail } from "@/services/ingestion-service";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { addFileLog, setFileExtra } from "@/test/server-areas/files";
import { appendLogLines, setLogExtra, type LogExtra } from "@/test/server-areas/ingestion-logs";
import { waitUntil } from "@/test/wait-until";
import { ParsingDetailsSheet } from "./parsing-details-sheet";

useFilesServer();

const logUrl = (id: string) => `/api/v1/datasets/${DATASET_ID}/ingestions/${id}`;
const idOf = (n: number) => `log${String(n).padStart(29, "0")}`;

/** Seeds one log row for document `doc` and returns its id. */
function seed(n: number, doc: number, result: "running" | "done" | "failed" | "cancelled", extra: LogExtra = {}): string {
  const id = idOf(n);
  addFileLog(server, { id, docId: documentRow(doc).id, result });
  setLogExtra(server, id, extra);
  return id;
}

const FAILED_ERROR = { step: "embed", code: "provider_timeout", message: "timed out" };

interface HostProps {
  logId?: string | null;
  canParseAgain?: (log: IngestionLogDetail) => boolean;
  onParseAgain?: (documentId: string) => void;
}

function Host({ logId = null, canParseAgain, onParseAgain }: HostProps) {
  const [state, setState] = useState<{ logId: string | null; open: boolean }>({ logId, open: logId !== null });
  return (
    <>
      <button type="button" onClick={() => setState({ logId: idOf(1), open: true })}>
        open first
      </button>
      <button type="button" onClick={() => setState({ logId: idOf(2), open: true })}>
        open second
      </button>
      <ParsingDetailsSheet
        datasetId={DATASET_ID}
        logId={state.logId}
        open={state.open}
        onOpenChange={(open) => setState((current) => ({ ...current, open }))}
        canParseAgain={canParseAgain}
        onParseAgain={onParseAgain}
      />
    </>
  );
}

function renderSheet(props: HostProps = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Host {...props} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const sheet = () => screen.findByTestId("parsing-details");

describe("The content of a failed entry (UI-15, D-05, D-08)", () => {
  it("shows status, reason, retry line, the definition list, the provider message and the log", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "4" })];
    setFileExtra(server, documentRow(1).id, { pagesTotal: 10, pagesWithoutText: 4 });
    const startedAt = Date.UTC(2026, 9, 5, 12, 30, 0);
    const id = seed(1, 1, "failed", {
      attempts: 3,
      maxAttempts: 3,
      retried: true,
      startedAt,
      durationSeconds: 3.24,
      lines: ["Fetching the file", "Embedding batch 1"],
      error: { ...FAILED_ERROR, detail: "upstream said: slow down" },
    });
    renderSheet({ logId: id });
    const root = await sheet();
    expect(await within(root).findByTestId("details-status")).toHaveTextContent("Failed");
    expect(within(root).getByTestId("details-reason")).toHaveTextContent("The embedding provider timed out.");
    expect(within(root).getByTestId("details-retry")).toHaveTextContent("Stopped after 3 attempts.");
    expect(within(root).getByTestId("details-step")).toHaveTextContent("Creating embeddings");
    expect(within(root).getByTestId("details-attempts")).toHaveTextContent("3 of 3");
    expect(within(root).getByTestId("details-started")).toHaveTextContent(new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(startedAt)));
    expect(within(root).getByTestId("details-duration")).toHaveTextContent("3.2 s");
    expect(within(root).getByTestId("details-chunks")).toHaveTextContent("0");
    expect(within(root).getByTestId("details-pages")).toHaveTextContent("4 of 10");
    expect(within(root).getByTestId("details-provider-message")).toHaveTextContent("upstream said: slow down");
    const log = within(root).getByRole("region", { name: "Progress log" });
    expect(log).toHaveAttribute("tabindex", "0");
    expect(log.className).toContain("max-h-80");
    expect(log).toHaveTextContent("Fetching the file");
    expect(log).toHaveTextContent("Embedding batch 1");
    expect(within(root).getByRole("heading", { name: "Parsing details" })).toBeInTheDocument();
    expect(root).toHaveTextContent("report-01.pdf");
  });

  it("says a failure that can never succeed was not retried", async () => {
    const id = seed(1, 1, "failed", { error: { step: "parse", code: "no_readable_text", message: "x" } });
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-retry")).toHaveTextContent("Not retried, because trying again would give the same result.");
    expect(screen.getByTestId("details-step")).toHaveTextContent("Reading the file");
  });

  it("draws no retry line for a failure that may still succeed and was not retried to the cap", async () => {
    const id = seed(1, 1, "failed", { attempts: 1, error: { step: "fetch", code: "worker_lost", message: "x" } });
    renderSheet({ logId: id });
    await screen.findByTestId("details-reason");
    expect(screen.queryByTestId("details-retry")).toBeNull();
  });

  it("shows no failed step, reason or retry line for a finished entry and no pages line outside PDFs", async () => {
    const id = seed(1, 1, "done", { lines: ["Done"], chunkCount: 7 });
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 7 })];
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-status")).toHaveTextContent("Finished");
    for (const testId of ["details-reason", "details-retry", "details-step", "details-pages", "details-provider-message"]) expect(screen.queryByTestId(testId), testId).toBeNull();
    expect(screen.getByTestId("details-chunks")).toHaveTextContent("7");
  });

  it("shows one decimal below ten seconds and whole seconds from ten", async () => {
    const a = seed(1, 1, "done", { durationSeconds: 9.96 });
    renderSheet({ logId: a });
    expect(await screen.findByTestId("details-duration")).toHaveTextContent("10 s");
    const b = seed(2, 2, "done", { durationSeconds: 42.4 });
    await userEvent.click(screen.getByRole("button", { name: "open second" }));
    expect(b).toBe(idOf(2));
    await waitFor(() => expect(screen.getByTestId("details-duration")).toHaveTextContent("42 s"));
  });
});

describe("Fixed copy for every code and step (D-08, D-23)", () => {
  it.each(FAILURE_CODES)("maps the code %s to its fixed sentence", async (code) => {
    const id = seed(1, 1, "failed", { error: { step: "embed", code, message: "server text that must not show" } });
    renderSheet({ logId: id });
    const reason = await screen.findByTestId("details-reason");
    expect(reason).toHaveTextContent(i18n.t(failureReasonKey(code)));
    expect(reason).not.toHaveTextContent("server text that must not show");
  });

  it.each(STEPS)("maps the step %s to its label", async (step) => {
    const id = seed(1, 1, "failed", { error: { step, code: "provider_timeout", message: "x" } });
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-step")).toHaveTextContent(i18n.t(failureStepKey(step)));
  });

  it("names an unknown step 'Unknown step'", async () => {
    const id = seed(1, 1, "failed", { error: { step: "mystery", code: "provider_timeout", message: "x" } });
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-step")).toHaveTextContent("Unknown step");
  });

  it("shows the server's message for an unknown code of 1 to 300 characters", async () => {
    const id = seed(1, 1, "failed", { error: { step: "embed", code: "brand_new", message: "A plain twenty chars" } });
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-reason")).toHaveTextContent("A plain twenty chars");
  });

  it.each([
    ["empty", ""],
    ["400 characters", "x".repeat(400)],
  ])("shows the unexpected-reason sentence for an unknown code with a %s message", async (_name, message) => {
    const id = seed(1, 1, "failed", { error: { step: "embed", code: "brand_new", message } });
    renderSheet({ logId: id });
    const reason = await screen.findByTestId("details-reason");
    expect(reason).toHaveTextContent("Parsing failed for an unexpected reason.");
    expect(reason.textContent).not.toContain("xxxx");
  });

  it("renders a hostile log line and provider message as text and creates no element (T-04-28-01)", async () => {
    const hostile = "<img src=x onerror=alert(1)> /ragflow/secret";
    const id = seed(1, 1, "failed", { lines: [hostile], error: { ...FAILED_ERROR, detail: "<b>bold</b>" } });
    const { container } = renderSheet({ logId: id });
    const log = await screen.findByRole("region", { name: "Progress log" });
    expect(log.textContent).toContain(hostile);
    expect(screen.getByTestId("details-provider-message").textContent).toContain("<b>bold</b>");
    expect(document.body.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(document.body.querySelector("[data-testid=parsing-details] b")).toBeNull();
  });
});

describe("States (UI-SPEC 'Parsing details panel')", () => {
  it("shows list skeletons and a 160px log skeleton while loading", async () => {
    const id = seed(1, 1, "failed", { error: FAILED_ERROR });
    server.holds[`GET ${logUrl(id)}`] = new Promise<void>(() => {});
    renderSheet({ logId: id });
    const root = await sheet();
    expect(within(root).getAllByTestId("details-skeleton").length).toBeGreaterThan(2);
    expect(within(root).getByTestId("details-log-skeleton").className).toContain("h-40");
  });

  it("shows an in-sheet error with Try again that loads the entry", async () => {
    const id = seed(1, 1, "done", { lines: ["ok"] });
    server.forced[`GET ${logUrl(id)}`] = { status: 500, message: "boom" };
    renderSheet({ logId: id });
    const error = await screen.findByTestId("details-error");
    expect(error).toHaveTextContent("Couldn't load the parsing details.");
    delete server.forced[`GET ${logUrl(id)}`];
    await userEvent.click(within(error).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("details-status")).toHaveTextContent("Finished");
    expect(screen.queryByTestId("details-error")).toBeNull();
  });

  it("says the entry no longer exists on a 404, without a retry", async () => {
    renderSheet({ logId: idOf(99) });
    expect(await screen.findByText("This log entry no longer exists.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("says no progress messages were recorded for an empty log", async () => {
    const id = seed(1, 1, "done");
    renderSheet({ logId: id });
    expect(await screen.findByTestId("details-log-empty")).toHaveTextContent("No progress messages were recorded.");
  });

  it("does not carry an error from one entry to the next opening (FE-04)", async () => {
    seed(1, 1, "done", { lines: ["a"] });
    seed(2, 2, "done", { lines: ["b"] });
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2)];
    server.forced[`GET ${logUrl(idOf(1))}`] = { status: 500, message: "boom" };
    renderSheet();
    await userEvent.click(screen.getByRole("button", { name: "open first" }));
    expect(await screen.findByTestId("details-error")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("parsing-details")).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "open second" }));
    expect(await screen.findByTestId("details-status")).toBeInTheDocument();
    expect(screen.queryByTestId("details-error")).toBeNull();
  });

  it("mounts the body only while open and sends nothing before it opens", async () => {
    seed(1, 1, "done");
    renderSheet();
    expect(screen.queryByTestId("parsing-details")).toBeNull();
    expect(server.calls.filter((c) => String(c.url).includes("/ingestions/"))).toHaveLength(0);
  });
});

describe("Live entries (D-25)", () => {
  it("polls every 2 seconds while the entry runs, shows new lines and stops once it ends", async () => {
    const id = seed(1, 1, "running", { lines: ["first line"] });
    server.documents[DATASET_ID] = [documentRow(1, { run: "1" })];
    renderSheet({ logId: id });
    const log = await screen.findByRole("region", { name: "Progress log" });
    expect(await within(screen.getByTestId("details-status")).findByText("Parsing")).toBeInTheDocument();
    const calls = () => server.callsTo("GET", logUrl(id)).length;
    const first = calls();
    appendLogLines(server, id, ["second line"]);
    await waitUntil(() => log.textContent?.includes("second line"), { timeout: 6000, describe: "the polled line" });
    expect(calls()).toBeGreaterThan(first);

    const lastLog = server.callsTo("GET", logUrl(id));
    expect(lastLog.length).toBeGreaterThan(1);
    // The run ends: the next poll shows the final state and no further request is made.
    const row = server.areaState<{ logs: { id: string; result: string }[] }>("files", () => ({ logs: [] })).logs.find((l) => l.id === id);
    (row as { result: string }).result = "done";
    await waitUntil(() => screen.getByTestId("details-status").textContent?.includes("Finished"), { timeout: 6000, describe: "the finished state" });
    const settled = calls();
    await expect(waitUntil(() => calls() > settled, { timeout: 2600 })).rejects.toThrow(/timed out/);
  }, 20_000);

  it("follows new lines only when the reader is at the bottom", async () => {
    const id = seed(1, 1, "running", { lines: ["one"] });
    server.documents[DATASET_ID] = [documentRow(1, { run: "1" })];
    renderSheet({ logId: id });
    const log = await screen.findByRole("region", { name: "Progress log" });
    Object.defineProperty(log, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(log, "clientHeight", { configurable: true, get: () => 100 });

    // At the bottom: the box follows.
    log.scrollTop = 900;
    fireEvent.scroll(log);
    appendLogLines(server, id, ["two"]);
    await waitUntil(() => log.textContent?.includes("two"), { timeout: 6000, describe: "line two" });
    expect(log.scrollTop).toBe(1000);

    // Scrolled up: the box stays where the reader is.
    log.scrollTop = 200;
    fireEvent.scroll(log);
    appendLogLines(server, id, ["three"]);
    await waitUntil(() => log.textContent?.includes("three"), { timeout: 6000, describe: "line three" });
    expect(log.scrollTop).toBe(200);
  }, 20_000);
});

describe("Footer (R-152)", () => {
  const failedLog = () => seed(1, 1, "failed", { error: FAILED_ERROR });

  it("offers Parse again only when the owner says the caller may and Close always", async () => {
    const id = failedLog();
    const { unmount } = renderSheet({ logId: id, canParseAgain: () => false });
    await screen.findByTestId("details-status");
    expect(screen.queryByTestId("details-reparse")).toBeNull();
    expect(screen.getByTestId("details-close")).toHaveTextContent("Close");
    unmount();
    renderSheet({ logId: id });
    await screen.findByTestId("details-status");
    expect(screen.queryByTestId("details-reparse")).toBeNull();
  });

  it("closes first and sends the request to the owner only after the sheet has unmounted", async () => {
    const id = failedLog();
    const seen: string[] = [];
    const onParseAgain = vi.fn((documentId: string) => seen.push(`${documentId}:${screen.queryByTestId("parsing-details") === null ? "gone" : "present"}`));
    renderSheet({ logId: id, canParseAgain: (log) => log.result === "failed", onParseAgain });
    const button = await screen.findByTestId("details-reparse");
    expect(button).toHaveTextContent("Parse again");
    await userEvent.click(button);
    await waitFor(() => expect(onParseAgain).toHaveBeenCalledTimes(1));
    expect(seen).toEqual([`${documentRow(1).id}:gone`]);
  });

  it("closes from the Close button without asking to parse", async () => {
    const id = failedLog();
    const onParseAgain = vi.fn();
    renderSheet({ logId: id, canParseAgain: () => true, onParseAgain });
    await userEvent.click(await screen.findByTestId("details-close"));
    await waitFor(() => expect(screen.queryByTestId("parsing-details")).toBeNull());
    expect(onParseAgain).not.toHaveBeenCalled();
  });
});

