import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { listChunks } from "@/services/chunk-service";
import { listDocuments, updateDocumentSettings, uploadDocument, type DocumentView } from "@/services/document-service";
import { blankPdf, poisonDocx, textFile, thirteenPagePdf } from "@/test/live/documents";
import { createAccount, createWorld, destroyWorld, installBrowserShims, join, openApp, resetApp, type Account, type World } from "@/test/live/ingest-world";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

// The Phase 4 dataset page against the real stack (UI-13, UI-15, UI-19, E2E-05, E2E-06): the real routes, the real HTTP
// client, the real API, the real queue and the real executor container. Only the third-party embedding provider is the
// loopback fake; the real provider key never enters the browser tier (T-03-22-04). Documents are tiny (D-16).
const PDF_CHUNK_TOKENS = 25;
// The executor embeds and indexes 64 chunks per batch (INGEST_BATCH_SIZE), one batch at a time, so a document of four batches
// has chunks in the index while it is still running.
const BATCH = 64;
const CANCEL_CHUNKS = 200;
const FAILED_TRACE = /Traceback|\/ragflow|\/tmp|host\.docker\.internal|sk-[A-Za-z0-9]{10,}/;

let world: World;
let mate: Account;

const pagePath = () => `/dataset/files?id=${world.datasetId}`;
const rowOf = (name: string): HTMLElement | null => screen.queryAllByTestId("document-row").find((row) => (row.textContent ?? "").includes(name)) ?? null;
const statusOf = (row: HTMLElement): string => within(row).queryByTestId("document-status")?.textContent?.trim() ?? "";

/** Uploads through the real service as the owner and returns the stored document. */
async function upload(file: File, chunkTokenNum?: number): Promise<DocumentView> {
  setAuthorization(world.owner.session);
  try {
    const stored = await uploadDocument(world.datasetId, file);
    if (chunkTokenNum !== undefined) await updateDocumentSettings(world.datasetId, stored.id, { chunkTokenNum });
    return stored;
  } finally {
    removeAuthorization();
  }
}

/** The list the page reads, fetched as the owner: the truth the DOM is compared with. */
async function listed(): Promise<DocumentView[]> {
  // The page may be mounted as the same owner, so the token is set and left in place.
  setAuthorization(world.owner.session);
  return (await listDocuments({ datasetId: world.datasetId, page: 1, pageSize: 100, keywords: "" })).items;
}

const chunksIn = (name: string): number => Number(/(\d+) chunks?/.exec(within(rowOf(name) as HTMLElement).getByTestId("document-status-detail").textContent ?? "")?.[1] ?? -1);

beforeAll(async () => {
  installBrowserShims();
  world = await createWorld("ingest", "team");
  mate = await createAccount("mate");
  await join(world.owner, mate);
});

afterEach(() => {
  world.fake.delayMs = 0;
  world.fake.mode = "ok";
  resetApp();
});

afterAll(async () => {
  await destroyWorld(world);
});

describe("live Phase 4 journeys on the dataset page", () => {
  let pdfId = "";
  let firstCount = 0;

  it("takes the 13-page PDF from Not started through Parsing to Finished with a chunk count and no reload (UI-15, success criterion 1)", async () => {
    const user = userEvent.setup();
    const stored = await upload(thirteenPagePdf("thirteen.pdf"), PDF_CHUNK_TOKENS);
    pdfId = stored.id;
    world.fake.delayMs = 3000;
    await openApp(world.owner, pagePath());
    const page = await screen.findByTestId("dataset-page", {}, { timeout: 30_000 });
    const row = await waitUntil(() => rowOf("thirteen.pdf"), { describe: "the PDF row", timeout: 30_000 });
    expect(row.getAttribute("data-run")).toBe("0");
    expect(statusOf(row)).toBe("Not started");
    page.setAttribute("data-journey-marker", "kept");

    await user.click(within(row).getByRole("button", { name: "Parse thirteen.pdf" }));

    const seen: number[] = [];
    let sawParsing = false;
    await waitUntil(
      () => {
        const current = rowOf("thirteen.pdf");
        if (current === null) return false;
        if (statusOf(current) === "Parsing") sawParsing = true;
        const bar = within(current).queryByTestId("document-progress-bar");
        const now = bar?.getAttribute("aria-valuenow") ?? bar?.querySelector("[aria-valuenow]")?.getAttribute("aria-valuenow");
        if (current.getAttribute("data-run") === "1" && now !== null && now !== undefined) seen.push(Number(now));
        return current.getAttribute("data-run") === "3";
      },
      { describe: "the PDF row to reach Finished", timeout: 150_000, interval: 50 },
    );
    expect(sawParsing).toBe(true);
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((value) => value <= 99)).toBe(true);
    expect(seen.some((value) => value > 0)).toBe(true);
    expect(seen).toEqual([...seen].sort((a, b) => a - b));

    const done = rowOf("thirteen.pdf") as HTMLElement;
    expect(statusOf(done)).toBe("Finished");
    firstCount = chunksIn("thirteen.pdf");
    expect(firstCount).toBe(26);
    expect(within(done).getByTestId("document-progress")).toHaveTextContent("100%");
    expect(screen.getByTestId("dataset-page")).toBe(page);
    expect(page.getAttribute("data-journey-marker")).toBe("kept");
  }, 240_000);

  it("states the chunk count and 0 edited and 0 hand-added on Parse again, and ends with the same count (D-03, D-04)", async () => {
    const user = userEvent.setup();
    await openApp(world.owner, pagePath());
    const row = await waitUntil(() => rowOf("thirteen.pdf"), { describe: "the PDF row", timeout: 30_000 });
    expect(statusOf(row)).toBe("Finished");
    const before = (await listed()).find((document) => document.id === pdfId);
    const embeddingCalls = world.fake.paths.filter((path) => path === "/v1/embeddings").length;

    await user.click(within(row).getByTestId("document-more"));
    await user.click(await screen.findByTestId("document-menu-reparse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(within(dialog).getByTestId("reparse-chunks")).toHaveTextContent(String(firstCount));
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("0");
    expect(within(dialog).getByTestId("reparse-manual")).toHaveTextContent("0");
    await user.click(within(dialog).getByTestId("reparse-confirm"));

    const after = await waitUntil(
      async () => {
        const document = (await listed()).find((item) => item.id === pdfId);
        return document !== undefined && document.run === "3" && document.lastLogId !== before?.lastLogId ? document : null;
      },
      { describe: "the replacing parse to finish under a new log entry", timeout: 150_000, interval: 500 },
    );
    expect(after.chunkCount).toBe(firstCount);
    expect(world.fake.paths.filter((path) => path === "/v1/embeddings").length).toBeGreaterThan(embeddingCalls);
    await waitUntil(() => rowOf("thirteen.pdf")?.getAttribute("data-run") === "3" && chunksIn("thirteen.pdf") === firstCount, { describe: "the row to show the same count", timeout: 30_000 });
  }, 240_000);

  it("ends the poison file as Failed with a plain reason, and the details sheet states the failed step, three attempts and a clean log (D-05, D-08)", async () => {
    const user = userEvent.setup();
    await upload(poisonDocx("damaged.docx"));
    await openApp(world.owner, pagePath());
    const row = await waitUntil(() => rowOf("damaged.docx"), { describe: "the poison row", timeout: 30_000 });
    await user.click(within(row).getByRole("button", { name: "Parse damaged.docx" }));
    // Three attempts with the executor's own back-off: up to 120 seconds.
    await waitUntil(() => rowOf("damaged.docx")?.getAttribute("data-run") === "4", { describe: "the poison row to fail", timeout: 150_000, interval: 250 });
    const failed = rowOf("damaged.docx") as HTMLElement;
    expect(statusOf(failed)).toBe("Failed");
    expect(failed).toHaveTextContent("The file is damaged or incomplete and couldn't be opened.");

    await user.click(within(failed).getByTestId("document-details"));
    const sheet = await screen.findByTestId("parsing-details", {}, { timeout: 15_000 });
    await waitUntil(() => within(sheet).queryByTestId("details-step") !== null, { describe: "the details to load", timeout: 15_000 });
    expect(within(sheet).getByTestId("details-step")).toHaveTextContent("Reading the file");
    expect(within(sheet).getByTestId("details-reason")).toHaveTextContent("The file is damaged or incomplete and couldn't be opened.");
    expect(within(sheet).getByTestId("details-retry")).toHaveTextContent("Stopped after 3 attempts.");
    expect(within(sheet).getByTestId("details-attempts")).toHaveTextContent("3 of 3");
    const log = within(sheet).getByTestId("details-log").textContent ?? "";
    expect(log.length).toBeGreaterThan(0);
    expect(log).not.toMatch(FAILED_TRACE);
    expect(sheet.textContent ?? "").not.toMatch(FAILED_TRACE);
  }, 300_000);

  it("fails a PDF without a text layer at once with the D-14 sentence and 'Not retried' (D-14)", async () => {
    const user = userEvent.setup();
    await upload(blankPdf(2, "blank.pdf"));
    await openApp(world.owner, pagePath());
    const row = await waitUntil(() => rowOf("blank.pdf"), { describe: "the blank PDF row", timeout: 30_000 });
    await user.click(within(row).getByRole("button", { name: "Parse blank.pdf" }));
    await waitUntil(() => rowOf("blank.pdf")?.getAttribute("data-run") === "4", { describe: "the blank PDF to fail", timeout: 60_000, interval: 250 });
    const failed = rowOf("blank.pdf") as HTMLElement;
    expect(statusOf(failed)).toBe("Failed");
    expect(failed).toHaveTextContent("This PDF has no readable text; scanned documents are not supported yet.");
    await user.click(within(failed).getByTestId("document-details"));
    const sheet = await screen.findByTestId("parsing-details", {}, { timeout: 15_000 });
    await waitUntil(() => within(sheet).queryByTestId("details-retry") !== null, { describe: "the details to load", timeout: 15_000 });
    expect(within(sheet).getByTestId("details-retry")).toHaveTextContent("Not retried, because trying again would give the same result.");
    expect(within(sheet).getByTestId("details-attempts")).toHaveTextContent("1 of 3");
  }, 120_000);

  it("shows Cancelled or Partly indexed within 10 s of Cancel parsing, and Parse again then starts with no dialog (D-06, D-09)", async () => {
    const user = userEvent.setup();
    const stored = await upload(textFile(CANCEL_CHUNKS, "cancel.txt"));
    world.fake.delayMs = 1500;
    await openApp(world.owner, pagePath());
    const row = await waitUntil(() => rowOf("cancel.txt"), { describe: "the cancel row", timeout: 30_000 });
    await user.click(within(row).getByRole("button", { name: "Parse cancel.txt" }));
    // Part-way: some chunks are indexed and the rest are not.
    await waitUntil(
      async () => {
        setAuthorization(world.owner.session);
        const page = await listChunks({ datasetId: world.datasetId, docId: stored.id, page: 1, size: 1, keywords: "" });
        return page.total >= BATCH && page.total < CANCEL_CHUNKS;
      },
      { describe: "chunks to exist while the parse runs", timeout: 120_000, interval: 200 },
    );
    const running = rowOf("cancel.txt") as HTMLElement;
    await user.click(await waitUntil(() => within(rowOf("cancel.txt") ?? running).queryByRole("button", { name: "Cancel parsing cancel.txt" }), { describe: "the Cancel parsing button", timeout: 30_000 }));
    await waitUntil(() => rowOf("cancel.txt")?.getAttribute("data-run") === "2", { describe: "the row to read cancelled", timeout: 10_000, interval: 50 });
    expect(["Cancelled", "Partly indexed"]).toContain(statusOf(rowOf("cancel.txt") as HTMLElement));
    world.fake.delayMs = 0;

    // Wait for the executor to stop writing before starting again.
    let last = -1;
    let stable = 0;
    await waitUntil(
      async () => {
        const page = await listChunks({ datasetId: world.datasetId, docId: stored.id, page: 1, size: 1, keywords: "" });
        stable = page.total === last ? stable + 1 : 0;
        last = page.total;
        return stable >= 3;
      },
      { describe: "the chunk count to settle", timeout: 60_000, interval: 1000 },
    );
    const before = (await listed()).find((document) => document.id === stored.id);

    await user.click(within(rowOf("cancel.txt") as HTMLElement).getByRole("button", { name: "Parse cancel.txt again" }));
    await waitUntil(
      async () => {
        const document = (await listed()).find((item) => item.id === stored.id);
        return document !== undefined && document.run === "3" && document.lastLogId !== before?.lastLogId;
      },
      { describe: "the second parse to finish", timeout: 150_000, interval: 500 },
    );
    expect(screen.queryByTestId("reparse-dialog")).toBeNull();
    await waitUntil(() => rowOf("cancel.txt")?.getAttribute("data-run") === "3" && chunksIn("cancel.txt") === CANCEL_CHUNKS, { describe: "the row to read all its chunks", timeout: 30_000 });
  }, 400_000);

  it("shows a team member status and chunks and no parse, edit or switch control (D-02, D-10)", async () => {
    const user = userEvent.setup();
    await openApp(mate, pagePath());
    await screen.findByTestId("dataset-page", {}, { timeout: 30_000 });
    const row = await waitUntil(() => rowOf("thirteen.pdf"), { describe: "the PDF row for the teammate", timeout: 30_000 });
    expect(statusOf(row)).toBe("Finished");
    expect(chunksIn("thirteen.pdf")).toBe(firstCount);
    expect(within(row).getByTestId("document-progress")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /^Parse/ })).toBeNull();
    expect(within(row).queryByTestId("document-select")).toBeNull();
    expect(within(row).queryByTestId("document-search-switch")).toBeNull();
    expect(within(row).queryByTestId("document-delete")).toBeNull();
    expect(row).toHaveTextContent(/\b(On|Off)\b/);
    // The not-yet-parsed and failed rows offer the teammate nothing either.
    for (const other of screen.getAllByTestId("document-row")) {
      expect(within(other).queryByRole("button", { name: /^(Parse|Cancel parsing)/ })).toBeNull();
    }

    await user.click(within(row).getByTestId("document-more"));
    const menu = await screen.findByTestId("document-menu");
    expect(within(menu).getByTestId("document-menu-chunks")).toHaveTextContent("View chunks");
    expect(within(menu).getByTestId("document-menu-open")).toHaveTextContent("Open document");
    expect(within(menu).queryByTestId("document-menu-reparse")).toBeNull();
    expect(within(menu).queryByTestId("document-menu-chunking")).toBeNull();
    cleanup();
  }, 120_000);
});
