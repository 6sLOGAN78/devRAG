import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { DOCUMENT_VIEWER_ROUTE, chunkPath, datasetFilesPath, documentViewerPath } from "@/constants/app-paths";
import { http, registerQueryClient } from "@/services/http";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DATASET_ID, datasetRow, documentRow, membershipRow, storedMemberships, type DocumentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { contentUrl, holdDownloads, setFileContent, setTextContent } from "@/test/server-areas/content";
import { setFileExtra } from "@/test/server-areas/files";
import { waitUntil } from "@/test/wait-until";
import DocumentViewer from ".";

useFilesServer();

/** Document ids are 32 lowercase hex characters; the shared fixture ids are not. */
const DOC = "d".repeat(31) + "1";
const DETAIL_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}`;
const CONTENT_URL = contentUrl(DATASET_ID, DOC);
let router: ReturnType<typeof createMemoryRouter>;
let clicked: string[] = [];
const originalCreate = URL.createObjectURL;
const originalRevoke = URL.revokeObjectURL;
const originalClick = HTMLAnchorElement.prototype.click;

const location = () => `${router.state.location.pathname}${router.state.location.search}`;

function setDoc(over: Partial<DocumentRow> = {}): void {
  server.documents[DATASET_ID] = [documentRow(1, { id: DOC, run: "3", chunk_num: 4, ...over })];
}

function renderPage(entry = documentViewerPath(DATASET_ID, DOC)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  router = createMemoryRouter(
    [
      { path: DOCUMENT_VIEWER_ROUTE, element: <DocumentViewer /> },
      { path: "/dataset/files", element: <p data-testid="files-page">files</p> },
      { path: "/chunk", element: <p data-testid="chunk-page-stub">chunks</p> },
      { path: "/datasets", element: <p data-testid="gallery-page">gallery</p> },
    ],
    { initialEntries: [entry] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  clicked = [];
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:test/${++n}`) as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn();
  HTMLAnchorElement.prototype.click = function click(this: HTMLAnchorElement) {
    clicked.push(this.download);
  };
  setDoc();
});
afterEach(() => {
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
  HTMLAnchorElement.prototype.click = originalClick;
});

describe("Structure (UI-19)", () => {
  it("shows the back link, the name, two outline actions, the meta row and no primary button", async () => {
    setFileExtra(server, DOC, { preview: "pages", pagesTotal: 3 });
    renderPage();
    const page = await screen.findByTestId("viewer-page");
    expect(screen.getByTestId("viewer-back")).toHaveAttribute("href", datasetFilesPath(DATASET_ID));
    expect(screen.getByTestId("viewer-back")).toHaveTextContent("Reports");
    expect(within(page).getByRole("heading", { level: 1, name: "report-01.pdf" })).toBeInTheDocument();
    const chunks = screen.getByTestId("viewer-chunks-link");
    expect(chunks).toHaveAttribute("href", chunkPath(DATASET_ID, DOC));
    expect(chunks).toHaveTextContent("View chunks");
    const download = screen.getByTestId("viewer-download");
    expect(download).toHaveAccessibleName("Download report-01.pdf");
    for (const control of [chunks, download]) expect(control.className).not.toMatch(/(^|\s)bg-primary(\s|$)/);
    const meta = screen.getByTestId("viewer-meta");
    expect(meta.tagName).toBe("DL");
    for (const label of ["Type", "Size", "Uploaded", "Status", "Chunks", "Method"]) expect(within(meta).getByText(label)).toBeInTheDocument();
    expect(meta).toHaveTextContent("PDF");
    expect(meta).toHaveTextContent("1.5 KB");
    expect(meta).toHaveTextContent("General");
    expect(within(meta).getByTestId("document-status")).toHaveTextContent("Finished");
    expect(document.title).toBe("report-01.pdf - devRag");
  });
});

describe("PDF pages", () => {
  it("shows the pages in a centred column, also when none has readable text", async () => {
    setFileExtra(server, DOC, { preview: "pages", pagesTotal: 3, pagesWithoutText: 3 });
    renderPage();
    const pages = await screen.findByTestId("viewer-pages");
    expect(pages.className).toContain("max-w-4xl");
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-no-preview")).toBeNull();
  });

  it("takes the page from the address, clamps it, and writes a change back", async () => {
    setFileExtra(server, DOC, { preview: "pages", pagesTotal: 3 });
    const user = userEvent.setup();
    renderPage(`${documentViewerPath(DATASET_ID, DOC)}&page=99`);
    expect(await screen.findByText("Page 3 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => expect(location()).toContain("page=2"));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
  });
});

describe("Text, image and no-preview bodies", () => {
  it("shows an HTML file as its source: the script is text and no script element exists", async () => {
    setDoc({ name: "page.html", suffix: "html" });
    setTextContent(server, DOC, '<script>window.pwned = 1</script><h2>Heading</h2>');
    renderPage();
    const pre = await screen.findByTestId("viewer-text");
    expect(pre.textContent).toBe('<script>window.pwned = 1</script><h2>Heading</h2>');
    expect(pre.querySelector("*")).toBeNull();
    expect(document.querySelector("script, h2, iframe")).toBeNull();
  });

  it.each(["txt", "md", "csv", "json"])("shows a %s file as text and says when it was cut", async (suffix) => {
    setDoc({ name: `file.${suffix}`, suffix });
    setTextContent(server, DOC, "# not a heading", true);
    renderPage();
    expect((await screen.findByTestId("viewer-text")).textContent).toBe("# not a heading");
    expect(screen.getByTestId("viewer-text-cut")).toBeInTheDocument();
  });

  it.each(["png", "jpg"])("shows a %s file as the image itself", async (suffix) => {
    setDoc({ name: `photo.${suffix}`, suffix });
    setFileContent(server, DOC, suffix === "png" ? "image/png" : "image/jpeg");
    renderPage();
    const image = await screen.findByTestId("viewer-image");
    expect(image).toHaveAttribute("alt", `photo.${suffix}`);
    expect(screen.queryByTestId("viewer-pages")).toBeNull();
  });

  it("refuses an image answer of another type", async () => {
    setDoc({ name: "photo.png", suffix: "png" });
    setFileContent(server, DOC, "text/html");
    renderPage();
    expect(await screen.findByTestId("viewer-preview-error")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-image")).toBeNull();
    expect(screen.getByTestId("viewer-download")).toBeEnabled();
  });

  it("offers a download card for a DOCX that points to the chunks", async () => {
    setDoc({ name: "plan.docx", suffix: "docx" });
    renderPage();
    const card = await screen.findByTestId("viewer-no-preview");
    expect(card).toHaveTextContent("No preview for DOCX files");
    expect(card).toHaveTextContent("Download the file to open it, or view its chunks to see the text that was read from it.");
    expect(within(card).getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(server.callsTo("GET", CONTENT_URL)).toHaveLength(0);
  });

  it("offers a download card for a type with no parser", async () => {
    setDoc({ name: "song.mp3", suffix: "mp3" });
    setFileExtra(server, DOC, { parseable: false });
    renderPage();
    const card = await screen.findByTestId("viewer-no-preview");
    expect(card).toHaveTextContent("No preview for MP3 files");
    expect(card).toHaveTextContent(/^.*Download the file to open it\.(?!, )/);
    expect(card).not.toHaveTextContent("view its chunks");
  });
});

describe("Download", () => {
  it("shows progress, ignores a second press and saves under the document name", async () => {
    setDoc({ name: "plan.docx", suffix: "docx" });
    setFileContent(server, DOC, "application/octet-stream", 1000);
    const release = holdDownloads(server);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("viewer-no-preview");
    await user.click(screen.getByTestId("viewer-download"));
    await waitUntil(() => screen.getByTestId("viewer-download").textContent === "Downloading 50%", { describe: "progress text" });
    await user.click(screen.getByTestId("viewer-download"));
    expect(server.callsTo("GET", CONTENT_URL)).toHaveLength(1);
    await act(async () => release());
    await waitUntil(() => clicked.length === 1 && screen.getByTestId("viewer-download").textContent === "Download", { describe: "the end" });
    expect(clicked).toEqual(["plan.docx"]);
    expect(location()).toBe(documentViewerPath(DATASET_ID, DOC));
  });

  it("reports a failure and keeps the button usable", async () => {
    setDoc({ name: "plan.docx", suffix: "docx" });
    server.forced[`GET ${CONTENT_URL}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("viewer-no-preview");
    await user.click(screen.getByTestId("viewer-download"));
    expect(await screen.findByText("The file wasn't downloaded. Try again.")).toBeInTheDocument();
    expect(screen.getByTestId("viewer-download")).toBeEnabled();
    expect(clicked).toHaveLength(0);
  });
});

describe("States", () => {
  it("shows a preview failure in place and retries", async () => {
    setDoc({ name: "notes.txt", suffix: "txt" });
    server.forced[`GET ${CONTENT_URL}`] = { status: 500, message: "boom" };
    setTextContent(server, DOC, "back again");
    const user = userEvent.setup();
    renderPage();
    const error = await screen.findByTestId("viewer-preview-error");
    expect(error).toHaveTextContent("Couldn't load this preview.");
    expect(screen.getByTestId("viewer-download")).toBeEnabled();
    delete server.forced[`GET ${CONTENT_URL}`];
    await user.click(within(error).getByRole("button", { name: "Try again" }));
    expect((await screen.findByTestId("viewer-text")).textContent).toBe("back again");
  });

  it("shows the loading skeleton before the document arrives", async () => {
    let release: () => void = () => {};
    server.holds[`GET ${DETAIL_URL}`] = new Promise<void>((resolve) => (release = resolve));
    renderPage();
    expect(await screen.findByTestId("viewer-skeleton")).toBeInTheDocument();
    release();
    expect(await screen.findByTestId("viewer-page")).toBeInTheDocument();
  });

  it("answers a malformed id with the not-found block and no request", async () => {
    renderPage(`${DOCUMENT_VIEWER_ROUTE}?id=zzz&doc=${DOC}`);
    expect(await screen.findByTestId("viewer-not-found")).toHaveTextContent("Document not found");
    expect(server.calls.filter((c) => /datasets/.test(c.url ?? ""))).toHaveLength(0);
  });

  it("answers an unknown document with the same block", async () => {
    renderPage(documentViewerPath(DATASET_ID, "b".repeat(32)));
    const block = await screen.findByTestId("viewer-not-found");
    expect(block).toHaveTextContent("It may have been deleted, or it isn't shared with you.");
    expect(within(block).getByRole("link", { name: "Back to datasets" })).toBeInTheDocument();
  });

  it("shows a page-level error with Try again when the document cannot be loaded", async () => {
    server.forced[`GET ${DETAIL_URL}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderPage();
    const error = await screen.findByTestId("error-state");
    expect(error).toHaveTextContent("Couldn't load this document");
    delete server.forced[`GET ${DETAIL_URL}`];
    await user.click(within(error).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("viewer-page")).toBeInTheDocument();
  });

  it("binds the dataset's workspace before any request, so a deep link into a joined workspace works", async () => {
    const joined = [membershipRow("t1", "Ada's workspace", "owner", "Ada"), membershipRow("t9", "Grace's workspace", "normal", "Grace")];
    server.memberships = joined;
    server.datasets[DATASET_ID] = datasetRow({ tenant_id: "t9", created_by: "u1" });
    useWorkspaceStore.getState().reset();
    useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(joined));
    setDoc({ name: "notes.txt", suffix: "txt" });
    setTextContent(server, DOC, "joined");
    const seen: Array<string | null> = [];
    const base = server.adapter;
    http.defaults.adapter = (config) => {
      if ((config.url ?? "").endsWith("/content") || config.url === DETAIL_URL) seen.push(useWorkspaceStore.getState().activeTenantId);
      return base(config);
    };
    renderPage();
    expect((await screen.findByTestId("viewer-text")).textContent).toBe("joined");
    expect(seen.length).toBeGreaterThan(0);
    expect(new Set(seen)).toEqual(new Set(["t9"]));
    expect(screen.queryByTestId("gallery-page")).toBeNull();
  });
});
