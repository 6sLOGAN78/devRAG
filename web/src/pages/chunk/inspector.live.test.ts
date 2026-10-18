import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { getDocument, parseDocuments, updateDocumentSettings, uploadDocument } from "@/services/document-service";
import { textFile, thirteenPagePdf } from "@/test/live/documents";
import { blobBytes, createWorld, destroyWorld, imageSizeOf, installBrowserShims, installObjectUrls, openApp, resetApp, type World } from "@/test/live/ingest-world";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";

// The chunk inspector against the real stack (UI-16, UI-17, D-11, D-12): the real routes, the real page images rendered by
// the real API, the real chunk writes embedded through the loopback provider. jsdom neither decodes images nor lays out
// boxes, so the image is checked by the bytes behind its `blob:` address (the PNG or JPEG header) and the box by the
// percentages in its style; the real-Chrome tier (test_spa_ingestion_browser.py) measures pixels.
const PDF_CHUNK_TOKENS = 25;
const PDF_ASPECT = 595 / 842;

let world: World;
let pdfId = "";
let textId = "";

const inspectorPath = (docId: string) => `/chunk?id=${world.datasetId}&doc=${docId}`;
const cards = (): HTMLElement[] => screen.queryAllByTestId("chunk-card");
const cardTexts = (): string[] => cards().map((card) => within(card).getByTestId("chunk-text").textContent ?? "");
const percentOf = (value: string): number => Number.parseFloat(value.replace("%", ""));

async function parsedAndFinished(docId: string): Promise<void> {
  await parseDocuments(world.datasetId, [docId], "1");
  await waitUntil(async () => (await getDocument(world.datasetId, docId)).run === "3", { describe: `document ${docId} to finish`, timeout: 150_000, interval: 500 });
}

async function typeInto(user: ReturnType<typeof userEvent.setup>, text: string): Promise<void> {
  const field = (await screen.findByTestId("chunk-editor-text")) as HTMLTextAreaElement;
  await user.clear(field);
  await user.click(field);
  await user.paste(text);
  expect(field.value).toBe(text);
}

beforeAll(async () => {
  installBrowserShims();
  installObjectUrls();
  world = await createWorld("inspect");
  setAuthorization(world.owner.session);
  const pdf = await uploadDocument(world.datasetId, thirteenPagePdf("thirteen.pdf"));
  pdfId = pdf.id;
  await updateDocumentSettings(world.datasetId, pdfId, { chunkTokenNum: PDF_CHUNK_TOKENS });
  const text = await uploadDocument(world.datasetId, textFile(3, "notes.txt"));
  textId = text.id;
  await parsedAndFinished(pdfId);
  await parsedAndFinished(textId);
  resetApp();
}, 300_000);

afterEach(() => {
  world.fake.delayMs = 0;
  world.fake.mode = "ok";
  resetApp();
});

afterAll(async () => {
  await destroyWorld(world);
});

describe("live chunk inspector (UI-16, UI-17)", () => {
  it("loads the page image, keeps the selected chunk's box inside it, and changes the image for a chunk on page 13 (UI-16, success criterion 2)", async () => {
    const user = userEvent.setup();
    await openApp(world.owner, inspectorPath(pdfId));
    await waitUntil(() => cards().length > 0, { describe: "the chunk cards", timeout: 30_000 });
    expect(await screen.findByTestId("preview-caption")).toHaveTextContent("Page 1 of 13");

    const first = await waitUntil(
      () => {
        const image = screen.queryByTestId("preview-image") as HTMLImageElement | null;
        return image !== null && image.src.startsWith("blob:") ? image : null;
      },
      { describe: "the page image with a blob address", timeout: 30_000 },
    );
    const firstAddress = first.src;
    const bytes = await blobBytes(firstAddress);
    const size = bytes === null ? null : imageSizeOf(bytes);
    expect(size).not.toBeNull();
    expect(size?.width ?? 0).toBeGreaterThan(0);
    expect(size?.height ?? 0).toBeGreaterThan(0);
    expect((size?.width ?? 1) / (size?.height ?? 1)).toBeCloseTo(PDF_ASPECT, 2);

    await user.click(within(cards()[0]).getByTestId("chunk-select"));
    const box = await screen.findByTestId("preview-box");
    const left = percentOf(box.style.left);
    const top = percentOf(box.style.top);
    const width = percentOf(box.style.width);
    const height = percentOf(box.style.height);
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(left + width).toBeLessThanOrEqual(100.01);
    expect(top + height).toBeLessThanOrEqual(100.01);
    // The box is drawn inside the wrapper that holds the image, so it moves with it.
    expect(box.parentElement).toBe(screen.getByTestId("preview-image").parentElement);

    // Page 13 is on the second list page: 26 chunks, 20 to a page.
    await user.click(within(screen.getByRole("navigation", { name: "Chunk pages" })).getByRole("button", { name: "Next" }));
    const onLast = await waitUntil(
      () => cards().find((card) => within(card).queryAllByTestId("chunk-page-chip").some((chip) => chip.textContent === "Page 13")) ?? null,
      { describe: "a chunk card with a Page 13 chip", timeout: 30_000 },
    );
    await user.click(within(onLast).getByTestId("chunk-select"));
    await waitUntil(() => screen.getByTestId("preview-caption").textContent === "Page 13 of 13", { describe: "the caption to read Page 13 of 13" });
    const second = await waitUntil(
      () => {
        const image = screen.queryByTestId("preview-image") as HTMLImageElement | null;
        return image !== null && image.src.startsWith("blob:") && image.src !== firstAddress ? image : null;
      },
      { describe: "the page image to change", timeout: 30_000 },
    );
    expect(second.getAttribute("alt")).toBe("Page 13 of thirteen.pdf");
    const secondBytes = await blobBytes(second.src);
    expect(secondBytes === null ? null : imageSizeOf(secondBytes)).not.toBeNull();
    await waitUntil(() => screen.queryAllByTestId("preview-box").length > 0, { describe: "the box on page 13", timeout: 15_000 });
  }, 120_000);

  it("keeps an edit, an added chunk and a switched-off chunk across a fresh load, and lists the off chunk under Off (UI-17, D-12)", async () => {
    const user = userEvent.setup();
    await openApp(world.owner, inspectorPath(textId));
    await waitUntil(() => cards().length === 3, { describe: "three chunk cards", timeout: 30_000 });

    // Edit chunk 1.
    const edited = "edited by the live journey about quasars";
    await user.click(within(cards()[0]).getByTestId("chunk-edit"));
    await typeInto(user, edited);
    await user.click(screen.getByTestId("chunk-editor-save"));
    await waitUntil(() => screen.queryByTestId("chunk-editor") === null && cardTexts()[0] === edited, { describe: "the edit to be saved and shown", timeout: 45_000 });
    expect(within(cards()[0]).getByTestId("chunk-badge-edited")).toBeInTheDocument();

    // Add a chunk by hand: it is last, selected, and badged.
    const added = "added by hand in the live journey about harbors";
    await user.click(screen.getByTestId("chunk-add"));
    await typeInto(user, added);
    await user.click(screen.getByTestId("chunk-editor-save"));
    await waitUntil(() => cards().length === 4 && cardTexts()[3] === added, { describe: "the added chunk to be last", timeout: 45_000 });
    expect(within(cards()[3]).getByTestId("chunk-badge-manual")).toBeInTheDocument();

    // Switch chunk 2 off.
    const switchedOffText = cardTexts()[1];
    await user.click(within(cards()[1]).getByTestId("chunk-switch"));
    await waitUntil(() => within(cards()[1]).queryByTestId("chunk-badge-off") !== null, { describe: "chunk 2 to carry the Off badge", timeout: 30_000 });

    // A page load from scratch: nothing is remembered by the SPA.
    await openApp(world.owner, inspectorPath(textId));
    await waitUntil(() => cards().length === 4, { describe: "four chunk cards after the reload", timeout: 30_000 });
    const texts = cardTexts();
    expect(texts[0]).toBe(edited);
    expect(texts[3]).toBe(added);
    expect(within(cards()[0]).getByTestId("chunk-badge-edited")).toBeInTheDocument();
    expect(within(cards()[3]).getByTestId("chunk-badge-manual")).toBeInTheDocument();
    expect(within(cards()[1]).getByTestId("chunk-badge-off")).toBeInTheDocument();
    expect(cards().filter((card) => card.getAttribute("data-enabled") === "false")).toHaveLength(1);

    await user.click(screen.getByTestId("chunk-filter-off"));
    await waitUntil(() => cards().length === 1, { describe: "the Off filter to list one chunk", timeout: 30_000 });
    expect(cardTexts()).toEqual([switchedOffText]);
    expect(within(cards()[0]).getByTestId("chunk-badge-off")).toBeInTheDocument();
  }, 180_000);

  it("keeps the typed text and shows the reason when the provider refuses a save (D-11)", async () => {
    const user = userEvent.setup();
    await openApp(world.owner, inspectorPath(textId));
    await waitUntil(() => cards().length === 4, { describe: "four chunk cards", timeout: 30_000 });
    const before = cardTexts();
    const typed = "text the provider will refuse about glaciers";
    world.fake.mode = "refuse";
    await user.click(within(cards()[2]).getByTestId("chunk-edit"));
    await typeInto(user, typed);
    await user.click(screen.getByTestId("chunk-editor-save"));
    const refusal = await screen.findByTestId("chunk-editor-refusal", {}, { timeout: 45_000 });
    expect((refusal.textContent ?? "").trim().length).toBeGreaterThan(0);
    expect((screen.getByTestId("chunk-editor-text") as HTMLTextAreaElement).value).toBe(typed);
    expect(screen.getByTestId("chunk-editor")).toBeInTheDocument();

    // Nothing was stored: after a fresh load the chunk reads as before.
    world.fake.mode = "ok";
    await openApp(world.owner, inspectorPath(textId));
    await waitUntil(() => cards().length === 4, { describe: "four chunk cards after the reload", timeout: 30_000 });
    expect(cardTexts()).toEqual(before);
  }, 120_000);

  it("states 1 edited and 1 hand-added chunk when the document is parsed again (D-03, D-04)", async () => {
    const user = userEvent.setup();
    await openApp(world.owner, `/dataset/files?id=${world.datasetId}`);
    const row = await waitUntil(() => screen.queryAllByTestId("document-row").find((candidate) => (candidate.textContent ?? "").includes("notes.txt")) ?? null, {
      describe: "the notes.txt row",
      timeout: 30_000,
    });
    await user.click(within(row).getByTestId("document-more"));
    await user.click(await screen.findByTestId("document-menu-reparse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(within(dialog).getByTestId("reparse-chunks")).toHaveTextContent("4");
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("1");
    expect(within(dialog).getByTestId("reparse-manual")).toHaveTextContent("1");
    // The person keeps the chunks: nothing was replaced.
    await user.click(within(dialog).getByTestId("reparse-keep"));
    await waitUntil(() => screen.queryByTestId("reparse-dialog") === null, { describe: "the dialog to close" });
    expect((await getDocument(world.datasetId, textId)).chunkCount).toBe(4);
  }, 120_000);
});
