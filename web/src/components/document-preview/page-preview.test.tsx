import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { waitUntil } from "@/test/wait-until";
import { boxStyle } from "./box-geometry";
import { PagePreview, type PagePreviewProps, type PreviewSelection } from "./page-preview";
import { pageImageKey, usePageImage } from "./use-page-image";

useFilesServer();

const DOC = documentRow(1).id;
const A4: [number, number] = [595, 842];
const IMAGE_URL = (page: number) => `/api/v1/datasets/${DATASET_ID}/documents/${DOC}/pages/${page}/image`;
const imageCalls = () => server.calls.filter((c) => /\/pages\/\d+\/image$/.test(c.url ?? ""));

let made: string[] = [];
let revoked: string[] = [];
const createObjectURL = vi.fn((_blob: Blob) => {
  const url = `blob:test/${made.length + 1}`;
  made.push(url);
  return url;
});
const revokeObjectURL = vi.fn((url: string) => {
  revoked.push(url);
});
const scrollIntoView = vi.fn();
const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  made = [];
  revoked = [];
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  scrollIntoView.mockClear();
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
});
afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

function newClient(): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return client;
}

function Host(props: Partial<PagePreviewProps> & { start?: number }) {
  const { start = 1, ...rest } = props;
  const [page, setPage] = useState(start);
  return <PagePreview datasetId={DATASET_ID} docId={DOC} name="report-01.pdf" pages={13} pageSizes={{ "1": A4, "13": A4 }} selection={null} {...rest} page={page} onPageChange={setPage} />;
}

function show(props: Partial<PagePreviewProps> & { start?: number } = {}) {
  const client = newClient();
  const view = render(
    <QueryClientProvider client={client}>
      <Host {...props} />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const selection = (positions: PreviewSelection["positions"], number = 3): PreviewSelection => ({ chunkId: "c1", number, positions });
const box = (page: number, over = {}) => ({ page, x0: 59.5, top: 84.2, x1: 297.5, bottom: 100, ...over });

describe("boxStyle (UI-16, R-164)", () => {
  it("puts a position in percent of the page", () => {
    const style = boxStyle(box(1), A4);
    expect(style).not.toBeNull();
    expect(parseFloat(style!.left)).toBeCloseTo(10, 3);
    expect(parseFloat(style!.top)).toBeCloseTo(10, 3);
    expect(parseFloat(style!.width)).toBeCloseTo(40, 3);
    expect(parseFloat(style!.height)).toBeCloseTo(1.8765, 2);
    expect(style!.left.endsWith("%")).toBe(true);
  });

  it("clamps every value to 0..100 and never lets a box leave the page", () => {
    const style = boxStyle({ page: 1, x0: -50, x1: 9000, top: -5, bottom: 99999 }, A4)!;
    expect(style).toEqual({ left: "0%", top: "0%", width: "100%", height: "100%" });
    const edge = boxStyle({ page: 1, x0: 500, x1: 9000, top: 800, bottom: 9000 }, A4)!;
    expect(parseFloat(edge.left) + parseFloat(edge.width)).toBeLessThanOrEqual(100);
    expect(parseFloat(edge.top) + parseFloat(edge.height)).toBeLessThanOrEqual(100);
  });

  it("draws nothing for a non-finite number", () => {
    for (const bad of [NaN, Infinity, -Infinity]) {
      expect(boxStyle(box(1, { x0: bad }), A4)).toBeNull();
      expect(boxStyle(box(1, { top: bad }), A4)).toBeNull();
      expect(boxStyle(box(1, { x1: bad }), A4)).toBeNull();
      expect(boxStyle(box(1, { bottom: bad }), A4)).toBeNull();
    }
  });

  it("draws nothing for a box without area", () => {
    expect(boxStyle(box(1, { x1: 59.5 }), A4)).toBeNull();
    expect(boxStyle(box(1, { x1: 10 }), A4)).toBeNull();
    expect(boxStyle(box(1, { bottom: 84.2 }), A4)).toBeNull();
    expect(boxStyle(box(1, { bottom: 3 }), A4)).toBeNull();
  });

  it("draws nothing when the page size is missing, zero, negative or not finite", () => {
    expect(boxStyle(box(1), undefined)).toBeNull();
    expect(boxStyle(box(1), [0, 842])).toBeNull();
    expect(boxStyle(box(1), [595, -1])).toBeNull();
    expect(boxStyle(box(1), [NaN, 842])).toBeNull();
  });

  it("does not depend on the unit: the same position on a page twice as large is the same box", () => {
    const a = boxStyle(box(1), A4)!;
    const b = boxStyle({ page: 1, x0: 119, top: 168.4, x1: 595, bottom: 200 }, [1190, 1684])!;
    expect(b).toEqual(a);
  });
});

describe("usePageImage (UI-SPEC HTTP client rules)", () => {
  function wrapper(client: QueryClient) {
    return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }

  it("fetches a blob, makes an object URL and revokes the previous one when the page changes", async () => {
    const client = newClient();
    const view = renderHook(({ page }) => usePageImage(DATASET_ID, DOC, page), { wrapper: wrapper(client), initialProps: { page: 1 } });
    await waitUntil(() => view.result.current.url !== null, { describe: "first page url" });
    expect(view.result.current.url).toBe("blob:test/1");
    view.rerender({ page: 2 });
    expect(view.result.current.url).toBeNull();
    await waitUntil(() => view.result.current.url === "blob:test/2", { describe: "second page url" });
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test/1");
    view.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test/2");
  });

  it("keys the query by workspace, dataset, document and page and keeps it for a minute", async () => {
    const client = newClient();
    const view = renderHook(() => usePageImage(DATASET_ID, DOC, 4), { wrapper: wrapper(client) });
    await waitUntil(() => view.result.current.url !== null);
    const query = client.getQueryCache().find({ queryKey: pageImageKey("t1", DATASET_ID, DOC, 4) });
    expect(query).toBeDefined();
    expect(pageImageKey("t1", DATASET_ID, DOC, 4)).toEqual(["ws", "t1", "page-image", DATASET_ID, DOC, 4]);
    expect(query!.options.gcTime).toBe(60000);
    expect((query!.options as { staleTime?: number }).staleTime).toBe(Infinity);
  });

  it("sends no request while disabled and reports an error with a working refetch", async () => {
    const client = newClient();
    const view = renderHook(({ enabled }) => usePageImage(DATASET_ID, DOC, 1, enabled), { wrapper: wrapper(client), initialProps: { enabled: false } });
    expect(imageCalls()).toHaveLength(0);
    server.forced[`GET ${IMAGE_URL(1)}`] = { status: 500, message: "boom" };
    view.rerender({ enabled: true });
    await waitUntil(() => view.result.current.isError, { describe: "error" });
    delete server.forced[`GET ${IMAGE_URL(1)}`];
    await act(async () => {
      view.result.current.refetch();
    });
    await waitUntil(() => view.result.current.url !== null, { describe: "url after retry" });
    expect(view.result.current.isError).toBe(false);
  });
});

describe("PagePreview toolbar (UI-16)", () => {
  it("renders a labelled region, a page nav and the caption as a polite live region", async () => {
    show();
    const region = screen.getByRole("region", { name: "Page preview" });
    expect(region).toHaveAttribute("data-testid", "page-preview");
    expect(within(region).getByRole("navigation", { name: "Document pages" })).toBeInTheDocument();
    const caption = screen.getByTestId("preview-caption");
    expect(caption).toHaveTextContent("Page 1 of 13");
    expect(caption).toHaveAttribute("aria-live", "polite");
    await screen.findByTestId("preview-image");
  });

  it("marks the ends with aria-disabled and moves one page at a time", async () => {
    const user = userEvent.setup();
    show();
    const previous = screen.getByTestId("preview-prev");
    const next = screen.getByTestId("preview-next");
    expect(previous).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveAttribute("aria-disabled", "false");
    await user.click(previous);
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 1 of 13");
    await user.click(next);
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 2 of 13");
    await waitUntil(() => imageCalls().some((c) => c.url === IMAGE_URL(2)), { describe: "page 2 requested" });
    await user.click(previous);
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 1 of 13");
  });

  it("disables next on the last page", async () => {
    show({ start: 13 });
    expect(screen.getByTestId("preview-next")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("preview-prev")).toHaveAttribute("aria-disabled", "false");
    await screen.findByTestId("preview-image");
  });

  it("zooms through 100, 150, 200 and 300 percent and fits back to 100", async () => {
    const user = userEvent.setup();
    show();
    const level = screen.getByTestId("preview-zoom-level");
    const wrapperOf = () => screen.getByTestId("preview-scroll").firstElementChild as HTMLElement;
    expect(level).toHaveTextContent("100%");
    expect(wrapperOf().style.width).toBe("100%");
    await user.click(screen.getByTestId("preview-zoom-in"));
    expect(level).toHaveTextContent("150%");
    await user.click(screen.getByTestId("preview-zoom-in"));
    await user.click(screen.getByTestId("preview-zoom-in"));
    expect(level).toHaveTextContent("300%");
    expect(wrapperOf().style.width).toBe("300%");
    expect(screen.getByTestId("preview-zoom-in")).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByTestId("preview-zoom-in"));
    expect(level).toHaveTextContent("300%");
    await user.click(screen.getByTestId("preview-zoom-out"));
    expect(level).toHaveTextContent("200%");
    await user.click(screen.getByTestId("preview-fit"));
    expect(level).toHaveTextContent("100%");
    expect(screen.getByTestId("preview-zoom-out")).toHaveAttribute("aria-disabled", "true");
    await screen.findByTestId("preview-image");
  });

  it("names the buttons", async () => {
    show();
    expect(screen.getByRole("button", { name: "Previous page" })).toBe(screen.getByTestId("preview-prev"));
    expect(screen.getByRole("button", { name: "Next page" })).toBe(screen.getByTestId("preview-next"));
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit width" })).toBeInTheDocument();
    await screen.findByTestId("preview-image");
  });
});

describe("PagePreview page area (UI-16)", () => {
  it("shows a focusable scroll container, the page aspect ratio and a described image", async () => {
    show();
    const scroll = screen.getByTestId("preview-scroll");
    expect(scroll).toHaveAttribute("tabindex", "0");
    const wrapper = scroll.firstElementChild as HTMLElement;
    expect(wrapper.style.aspectRatio.replace(/\s/g, "")).toBe("595/842");
    const image = await screen.findByTestId("preview-image");
    expect(image).toHaveAttribute("alt", "Page 1 of report-01.pdf");
    expect(image).toHaveAttribute("draggable", "false");
    expect(image).toHaveAttribute("src", "blob:test/1");
  });

  it("uses 1:1.414 until the page size is known", async () => {
    show({ pageSizes: {} });
    const wrapper = screen.getByTestId("preview-scroll").firstElementChild as HTMLElement;
    expect(wrapper.style.aspectRatio.replace(/\s/g, "")).toBe("1/1.414");
    await screen.findByTestId("preview-image");
  });

  it("shows a skeleton with the page's shape while the image loads, then the image", async () => {
    let release!: () => void;
    server.holds[`GET ${IMAGE_URL(1)}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    show();
    expect(await screen.findByTestId("preview-skeleton")).toBeInTheDocument();
    expect(screen.queryByTestId("preview-image")).toBeNull();
    expect(screen.getByTestId("preview-next")).toBeInTheDocument();
    release();
    await screen.findByTestId("preview-image");
    expect(screen.queryByTestId("preview-skeleton")).toBeNull();
  });

  it("says the page could not be loaded and retries from a ghost button", async () => {
    server.forced[`GET ${IMAGE_URL(1)}`] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    show();
    const failed = await screen.findByTestId("preview-error");
    expect(failed).toHaveTextContent("Couldn't load page 1.");
    delete server.forced[`GET ${IMAGE_URL(1)}`];
    await user.click(within(failed).getByRole("button", { name: "Try again" }));
    await screen.findByTestId("preview-image");
    expect(screen.queryByTestId("preview-error")).toBeNull();
    expect(screen.getByTestId("preview-next")).not.toHaveAttribute("aria-disabled", "true");
  });

  it("renders nothing for a page count of 0 or an unknown one", () => {
    const zero = show({ pages: 0 });
    expect(zero.container).toBeEmptyDOMElement();
    zero.unmount();
    const unknown = show({ pages: null });
    expect(unknown.container).toBeEmptyDOMElement();
    expect(imageCalls()).toHaveLength(0);
  });

  it("clamps a page outside 1..pages", async () => {
    show({ start: 40 });
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 13 of 13");
    await waitUntil(() => imageCalls().some((c) => c.url === IMAGE_URL(13)));
    expect(imageCalls().some((c) => c.url === IMAGE_URL(40))).toBe(false);
  });
});

describe("PagePreview boxes (UI-16, R-164)", () => {
  it("draws the selected chunk's boxes on the shown page in percent, hidden from assistive technology and inert", async () => {
    show({ selection: selection([box(1)]) });
    const drawn = await screen.findByTestId("preview-box");
    expect(drawn).toHaveAttribute("aria-hidden", "true");
    expect(drawn.style.left).toBe("10%");
    expect(drawn.style.top).toBe("10%");
    expect(drawn.style.width).toBe("40%");
    expect(parseFloat(drawn.style.height)).toBeCloseTo(1.8765, 2);
    expect(drawn.style.pointerEvents).toBe("none");
    expect(drawn.style.minWidth).toBe("4px");
    expect(drawn.style.minHeight).toBe("4px");
    expect(screen.getByTestId("preview-scroll").firstElementChild).toContainElement(drawn);
  });

  it("draws only the boxes that lie on the shown page, and skips a box that cannot be drawn", async () => {
    show({ selection: selection([box(1), box(1, { x1: 10 }), box(1, { top: 300, bottom: 400 }), box(2)]) });
    await screen.findByTestId("preview-image");
    expect(screen.getAllByTestId("preview-box")).toHaveLength(2);
  });

  it("scrolls the first box into view when a chunk is selected, instantly under reduced motion", async () => {
    const view = show({ selection: null });
    await screen.findByTestId("preview-image");
    expect(scrollIntoView).not.toHaveBeenCalled();
    view.rerender(
      <QueryClientProvider client={view.client}>
        <Host selection={selection([box(1)])} />
      </QueryClientProvider>,
    );
    await waitUntil(() => scrollIntoView.mock.calls.length > 0, { describe: "scrolled" });
    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: "center", behavior: "smooth" }));
  });

  it("uses behavior auto when the reader prefers reduced motion", async () => {
    window.matchMedia = ((query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
    show({ selection: selection([box(1)]) });
    await waitUntil(() => scrollIntoView.mock.calls.length > 0);
    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("announces the selection with its page, or without one", async () => {
    const view = show({ selection: selection([box(1)], 7) });
    expect(screen.getByTestId("chunk-live")).toHaveAttribute("role", "status");
    expect(screen.getByTestId("chunk-live")).toHaveTextContent("Chunk 7: page 1");
    view.rerender(
      <QueryClientProvider client={view.client}>
        <Host selection={selection([], 8)} />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chunk-live")).toHaveTextContent("Chunk 8");
    expect(screen.getByTestId("chunk-live")).not.toHaveTextContent("page");
    await screen.findByTestId("preview-image");
  });

  it("tells the reader where the chunk is when another page is shown, and goes there on request", async () => {
    const user = userEvent.setup();
    show({ selection: selection([box(13)]), start: 1 });
    const note = await screen.findByTestId("preview-away-note");
    expect(note).toHaveTextContent("The selected chunk is on page 13.");
    expect(screen.queryByTestId("preview-box")).toBeNull();
    const goto = within(note).getByRole("button", { name: "Go to page 13" });
    expect(goto).toHaveAttribute("data-testid", "preview-goto");
    await user.click(goto);
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 13 of 13");
    expect(await screen.findByTestId("preview-box")).toBeInTheDocument();
    expect(screen.queryByTestId("preview-away-note")).toBeNull();
  });

  it("names the first page of a chunk that spans pages, and shows each page's own boxes", async () => {
    const user = userEvent.setup();
    show({ selection: selection([box(1), box(2), box(2, { top: 300, bottom: 360 })]), start: 5, pageSizes: { "1": A4, "2": A4 } });
    expect(await screen.findByTestId("preview-away-note")).toHaveTextContent("The selected chunk is on page 1.");
    await user.click(screen.getByTestId("preview-goto"));
    expect(await screen.findAllByTestId("preview-box")).toHaveLength(1);
    await user.click(screen.getByTestId("preview-next"));
    await waitFor(() => expect(screen.getAllByTestId("preview-box")).toHaveLength(2));
  });

  it("says a hand-added chunk has no place on a page, keeps the page and draws no box", async () => {
    show({ selection: selection([]), start: 4 });
    expect(await screen.findByTestId("preview-away-note")).toHaveTextContent("This chunk was added by hand and has no place on a page.");
    expect(screen.queryByTestId("preview-goto")).toBeNull();
    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("Page 4 of 13");
  });

  it("shows no note and no box without a selection", async () => {
    show();
    await screen.findByTestId("preview-image");
    expect(screen.queryByTestId("preview-away-note")).toBeNull();
    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(screen.queryByTestId("chunk-live")).toBeEmptyDOMElement();
  });

  it("draws nothing for hostile numbers and never puts them in a style string", async () => {
    show({ selection: selection([{ page: 1, x0: Number.NaN, top: 0, x1: 10, bottom: 10 }, box(1, { x1: Number.POSITIVE_INFINITY })]) });
    await screen.findByTestId("preview-image");
    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(document.body.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("keeps its own boxes aligned when the zoom changes (they stay in percent of the wrapper)", async () => {
    const user = userEvent.setup();
    show({ selection: selection([box(1)]) });
    await screen.findByTestId("preview-box");
    await user.click(screen.getByTestId("preview-zoom-in"));
    expect((await screen.findByTestId("preview-box")).style.left).toBe("10%");
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });
});
