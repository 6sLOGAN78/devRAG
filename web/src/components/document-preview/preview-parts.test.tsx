import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { contentUrl, holdDownloads, setFileContent, setTextContent } from "@/test/server-areas/content";
import { waitUntil } from "@/test/wait-until";
import { ImagePreview } from "./image-preview";
import { TextPreview } from "./text-preview";
import { useBlobUrl } from "./use-blob-url";
import { useDownload } from "./use-download";

useFilesServer();

const DOC = documentRow(1).id;
const URL_OF = contentUrl(DATASET_ID, DOC);
const NAME = "report-01.pdf";

let made: string[] = [];
let revoked: string[] = [];
let clicked: { download: string; href: string }[] = [];
const originalCreate = URL.createObjectURL;
const originalRevoke = URL.revokeObjectURL;
const originalClick = HTMLAnchorElement.prototype.click;

beforeEach(() => {
  made = [];
  revoked = [];
  clicked = [];
  URL.createObjectURL = vi.fn(() => {
    const url = `blob:test/${made.length + 1}`;
    made.push(url);
    return url;
  }) as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn((url: string) => {
    revoked.push(url);
  });
  HTMLAnchorElement.prototype.click = function click(this: HTMLAnchorElement) {
    clicked.push({ download: this.download, href: this.href });
  };
});
afterEach(() => {
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
  HTMLAnchorElement.prototype.click = originalClick;
});

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      {children}
      <Toaster />
    </QueryClientProvider>
  );
}

const png = () => new Blob([new Uint8Array(4)], { type: "image/png" });

describe("useBlobUrl", () => {
  it("makes a URL for an image blob and nothing for another type or no blob", () => {
    const first = png();
    const { result, rerender } = renderHook(({ blob }: { blob: Blob | null }) => useBlobUrl(blob), { initialProps: { blob: null as Blob | null } });
    expect(result.current).toBeNull();
    rerender({ blob: first });
    expect(result.current).toBe("blob:test/1");
    rerender({ blob: new Blob(["<b>x</b>"], { type: "text/html" }) });
    expect(result.current).toBeNull();
    expect(made).toHaveLength(1);
  });

  it("revokes the previous URL when the blob changes and the last one on unmount", () => {
    const { result, rerender, unmount } = renderHook(({ blob }: { blob: Blob }) => useBlobUrl(blob), { initialProps: { blob: png() } });
    expect(result.current).toBe("blob:test/1");
    rerender({ blob: png() });
    expect(revoked).toEqual(["blob:test/1"]);
    expect(result.current).toBe("blob:test/2");
    unmount();
    expect(revoked).toEqual(["blob:test/1", "blob:test/2"]);
  });
});

describe("TextPreview", () => {
  it("shows a script and a heading marker as literal text and creates no element", async () => {
    setTextContent(server, DOC, "<script>alert(1)</script>\n# heading");
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} />, { wrapper: wrapper() });
    const pre = await screen.findByTestId("viewer-text");
    expect(pre.tagName).toBe("PRE");
    expect(pre.textContent).toBe("<script>alert(1)</script>\n# heading");
    expect(pre.querySelector("*")).toBeNull();
    expect(document.querySelector("script, h1")).toBeNull();
    expect(pre).toHaveAttribute("tabindex", "0");
    expect(pre).toHaveAccessibleName("File text");
    expect(pre.className).toContain("whitespace-pre-wrap");
    expect(screen.queryByTestId("viewer-text-cut")).toBeNull();
  });

  it("says so when the server cut the text", async () => {
    setTextContent(server, DOC, "start of the file", true);
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} />, { wrapper: wrapper() });
    expect(await screen.findByTestId("viewer-text-cut")).toHaveTextContent("Showing the first part of this file. Download it to see the rest.");
  });

  it("shows at most 262144 characters and says the rest was cut", async () => {
    setTextContent(server, DOC, "a".repeat(262144 + 10));
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} />, { wrapper: wrapper() });
    const pre = await screen.findByTestId("viewer-text");
    expect(pre.textContent).toHaveLength(262144);
    expect(screen.getByTestId("viewer-text-cut")).toBeInTheDocument();
  });

  it("says an empty file has no text", async () => {
    setTextContent(server, DOC, "");
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} />, { wrapper: wrapper() });
    expect(await screen.findByText("This file has no text.")).toBeInTheDocument();
  });

  it("shows the preview error with a retry that asks again", async () => {
    server.forced[`GET ${URL_OF}`] = { status: 500, message: "boom" };
    setTextContent(server, DOC, "recovered");
    const user = userEvent.setup();
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} />, { wrapper: wrapper() });
    const error = await screen.findByTestId("viewer-preview-error");
    expect(error).toHaveTextContent("Couldn't load this preview.");
    delete server.forced[`GET ${URL_OF}`];
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect((await screen.findByTestId("viewer-text")).textContent).toBe("recovered");
  });

  it("sends nothing while it is disabled", async () => {
    setTextContent(server, DOC, "x");
    render(<TextPreview datasetId={DATASET_ID} docId={DOC} enabled={false} />, { wrapper: wrapper() });
    await expect(waitUntil(() => server.callsTo("GET", URL_OF).length > 0, { timeout: 300, interval: 50 })).rejects.toThrow(/timed out/);
  });
});

describe("ImagePreview", () => {
  it("shows a PNG with the file name as its description", async () => {
    setFileContent(server, DOC, "image/png");
    render(<ImagePreview datasetId={DATASET_ID} docId={DOC} name="scan.png" />, { wrapper: wrapper() });
    const image = await screen.findByTestId("viewer-image");
    expect(image).toHaveAttribute("alt", "scan.png");
    expect(image).toHaveAttribute("src", "blob:test/1");
    expect(image.className).toContain("max-w-full");
  });

  it("never shows an answer of another type", async () => {
    setFileContent(server, DOC, "image/svg+xml");
    render(<ImagePreview datasetId={DATASET_ID} docId={DOC} name="evil.png" />, { wrapper: wrapper() });
    expect(await screen.findByTestId("viewer-preview-error")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-image")).toBeNull();
    expect(made).toHaveLength(0);
  });
});

function Download() {
  const { start, percent, busy } = useDownload(DATASET_ID, DOC, NAME);
  return (
    <>
      <button type="button" onClick={start}>
        go
      </button>
      <p data-testid="state">{`${busy}|${percent}`}</p>
    </>
  );
}

describe("useDownload", () => {
  it("reports progress, ignores a second press, saves under the document name and revokes the URL", async () => {
    setFileContent(server, DOC, "text/html", 1000);
    const release = holdDownloads(server);
    const user = userEvent.setup();
    render(<Download />, { wrapper: wrapper() });
    await user.click(screen.getByText("go"));
    await user.click(screen.getByText("go"));
    await waitUntil(() => screen.getByTestId("state").textContent === "true|50", { describe: "half the file" });
    expect(server.callsTo("GET", URL_OF)).toHaveLength(1);
    expect(server.callsTo("GET", URL_OF)[0]?.timeout).toBe(0);
    await act(async () => release());
    await waitUntil(() => screen.getByTestId("state").textContent === "false|null", { describe: "the end" });
    expect(clicked).toEqual([{ download: NAME, href: "blob:test/1" }]);
    expect(revoked).toEqual(["blob:test/1"]);
  });

  it("has no percent when the size is unknown", async () => {
    setFileContent(server, DOC, "application/pdf", 1000, false);
    const release = holdDownloads(server);
    const user = userEvent.setup();
    render(<Download />, { wrapper: wrapper() });
    await user.click(screen.getByText("go"));
    await waitUntil(() => screen.getByTestId("state").textContent === "true|null" && server.callsTo("GET", URL_OF).length === 1, { describe: "busy without a size" });
    await act(async () => release());
    await waitUntil(() => clicked.length === 1);
  });

  it("aborts the request when the component goes away and saves nothing", async () => {
    setFileContent(server, DOC, "application/pdf", 1000);
    const release = holdDownloads(server);
    const user = userEvent.setup();
    const view = render(<Download />, { wrapper: wrapper() });
    await user.click(screen.getByText("go"));
    await waitUntil(() => server.callsTo("GET", URL_OF).length === 1);
    const signal = server.callsTo("GET", URL_OF)[0]?.signal as AbortSignal;
    expect(signal.aborted).toBe(false);
    view.unmount();
    expect(signal.aborted).toBe(true);
    release();
    await expect(waitUntil(() => clicked.length > 0, { timeout: 300, interval: 50 })).rejects.toThrow(/timed out/);
  });

  it("reports a failure with the error toast and can be started again", async () => {
    server.forced[`GET ${URL_OF}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    render(<Download />, { wrapper: wrapper() });
    await user.click(screen.getByText("go"));
    expect(await screen.findByText("The file wasn't downloaded. Try again.")).toBeInTheDocument();
    expect(screen.getByTestId("state")).toHaveTextContent("false|null");
    expect(clicked).toHaveLength(0);
  });
});
