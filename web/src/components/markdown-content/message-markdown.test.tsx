import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { notifyError, notifySuccess } from "@/services/notify";
import { toReference } from "@/services/chat-service";
import { MessageMarkdown } from "./index";

vi.mock("@/services/notify", () => ({ notifyError: vi.fn(), notifySuccess: vi.fn() }));
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
const chunks = toReference({ chunks: [{ index: 0, doc_name: "Handbook" }, { index: 3, doc_name: "Report" }] }).chunks;
function show(text: string, props = {}) { return render(<MessageMarkdown text={text} chunks={chunks} onOpenSource={vi.fn()} {...props} />); }

describe("safe answer Markdown", () => {
  it.each(['<script>alert("x")</script>', '<img src="https://evil.invalid" onerror="alert(1)">', '<iframe src="https://evil.invalid"></iframe>'])("escapes raw HTML: %s", (text) => {
    const { container } = show(text); expect(container.querySelector("script,img,iframe")).toBeNull(); expect(container.textContent).toContain(text);
  });
  it.each(["javascript:alert(1)", "data:text/html,evil", "/datasets", "../x", "#top", "?q=x"])("renders an unsafe or relative link as text: %s", (url) => {
    const { container } = show(`[link](${url})`); expect(container.querySelector("a")).toBeNull(); expect(container.textContent).toContain("link");
  });
  it.each(["http://example.test/path", "https://example.test/path", "mailto:team@example.test"])("allows an absolute external link: %s", (url) => {
    show(`[link](${url})`); expect(screen.getByRole("link", { name: "link" })).toHaveAttribute("href", url);
    expect(screen.getByRole("link")).toHaveAttribute("target", "_blank"); expect(screen.getByRole("link")).toHaveAttribute("rel", "noopener noreferrer");
  });
  it("renders image alt text without creating a request-capable image", () => {
    const { container } = show("![diagram](https://evil.invalid/tracker.png)"); expect(screen.getByText("diagram")).toBeInTheDocument(); expect(container.querySelector("img")).toBeNull();
  });
  it("uses the file name when an image has no alt text", () => { show("![](https://evil.invalid/report.png?track=1)"); expect(screen.getByText("report.png")).toBeInTheDocument(); });
  it("wraps a GFM table for horizontal scrolling", () => {
    show("| A | B |\n|---|---|\n| one | two |"); expect(screen.getByRole("table").parentElement).toHaveClass("overflow-x-auto");
  });
  it("renders lists and keeps math as text", () => {
    show("- one\n- two\n\n$x+y$ and $$x=y$$"); expect(screen.getAllByRole("listitem")).toHaveLength(2); expect(screen.getByText(/\$x\+y\$/)).toBeInTheDocument();
  });
  it("keeps semantic headings at the body size and weight", () => {
    show("# Heading"); expect(screen.getByRole("heading", { level: 1 })).toHaveClass("text-base", "font-semibold");
  });
  it("copies a code block and reports success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined); Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    show("```js\nconst x = 1;\n```"); await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy code" })));
    expect(writeText).toHaveBeenCalledWith("const x = 1;\n"); expect(notifySuccess).toHaveBeenCalledWith("Code copied");
  });
  it("reports clipboard rejection", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied")); Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    show("```\ncode\n```"); await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy code" })));
    expect(notifyError).toHaveBeenCalledWith(expect.objectContaining({ title: "The code wasn't copied." }));
  });
  it("renders a sparse index as its one-based source pill and opens it", () => {
    const onOpenSource = vi.fn(); show("answer##3$$", { onOpenSource, openIndex: 3 });
    const pill = screen.getByRole("button", { name: "Source 4: Report" }); expect(pill).toHaveTextContent("4"); expect(pill).toHaveAttribute("data-cite-index", "3");
    fireEvent.click(pill); expect(onOpenSource).toHaveBeenCalledWith(3, pill);
  });
  it("deletes markers absent from the reference", () => { const { container } = show("answer##2$$"); expect(container.textContent).toBe("answer"); expect(screen.queryByTestId("cite-pill")).toBeNull(); });
  it("renders an unavailable source as an inert span", () => {
    show("answer##3$$", { chunks: [{ index: 3, unavailable: true }] }); expect(screen.getByTestId("cite-pill-unavailable").tagName).toBe("SPAN");
    expect(screen.getByText("Source 4 is no longer available to you")).toBeInTheDocument(); expect(screen.queryByRole("button")).toBeNull();
  });
  it("preserves marker text in inline and fenced code", () => {
    const { container } = show("`##0$$`\n\n```\n##3$$\n```"); expect(container.textContent).toContain("##0$$"); expect(container.textContent).toContain("##3$$"); expect(screen.queryByTestId("cite-pill")).toBeNull();
  });
  it("holds back a streaming partial marker then shows the completed pill", () => {
    const { container, rerender } = show("answer ##3$", { streaming: true }); expect(container.textContent).not.toContain("##3$");
    rerender(<MessageMarkdown text="answer ##3$$" chunks={chunks} streaming onOpenSource={vi.fn()} />); expect(screen.getByRole("button", { name: "Source 4: Report" })).toBeInTheDocument();
  });
  it("does not hold partial markers after the final frame", () => { const { container } = show("answer ##3$", { streaming: false }); expect(container.textContent).toContain("##3$"); });
});
