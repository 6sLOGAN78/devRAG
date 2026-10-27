import { QueryClientProvider } from "@tanstack/react-query";
import { chatRoot } from "@/hooks/use-chat-request";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toAssistantDetail, toMessage, toReference } from "@/services/chat-service";
import { http } from "@/services/http";
import { notifyError } from "@/services/notify";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { A, B, S, chatSetup } from "@/test/chat-page";
import { assistantRow } from "@/test/server-areas/assistants";
import { messageRow, setMessages, streamOf } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";
import { FeedbackButtons } from "./feedback-buttons";
import { MessageItem } from "./message-item";
import { SourceChips } from "./source-chips";

vi.mock("@/services/notify", () => ({ notifySuccess: vi.fn(), notifyError: vi.fn() }));
describe("citations and answer feedback", () => {
  const adapter = http.defaults.adapter; let context: ReturnType<typeof chatSetup>;
  const reference = { chunks: [{ index: 3, chunk_id: "fourth", doc_name: "fourth.pdf", content: "Fourth saved passage", positions: [{ page: 4, x0: 1, x1: 10, top: 1, bottom: 10 }] }, { index: 0, chunk_id: "first", doc_name: "first.txt", content: "First saved passage" }, { index: 2, unavailable: true }], doc_aggs: [] };
  const M = messageRow().id;
  beforeEach(() => { context = chatSetup(); vi.mocked(notifyError).mockClear(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  async function open(over = {}) {
    setMessages(context.server, S, [messageRow(1, { content: "First ##0$$ Fourth ##3$$", reference, ...over })]); const view = context.mount(`/chats?chat=${A}&session=${S}`); await waitUntil(() => screen.queryByTestId("message-assistant")); return view;
  }
  it("sorts distinct openable source chips by their own index", () => {
    const chunks = toReference(reference).chunks; render(<SourceChips chunks={[...chunks, chunks[0]!]} onOpen={vi.fn()} />);
    expect(screen.getAllByTestId("source-chip").map((node) => node.dataset.citeIndex)).toEqual(["0", "3"]); expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("Page 4");
  });
  it("does not draw chips for unavailable sources", () => { render(<SourceChips chunks={[{ index: 7, unavailable: true }]} onOpen={vi.fn()} />); expect(screen.queryByTestId("source-chips")).toBeNull(); });
  it("opens the drawer from a citation pill and restores focus to that pill", async () => {
    await open(); fireEvent.click(screen.getAllByTestId("cite-pill")[0]!); await waitUntil(() => screen.queryByTestId("source-passage")); expect(screen.getByTestId("source-passage")).toHaveTextContent("First saved passage"); expect(screen.getByTestId("source-passage")).toHaveFocus();
    expect(screen.getAllByTestId("cite-pill")[0]).toHaveAttribute("aria-pressed", "true"); fireEvent.click(screen.getByTestId("source-close")); await waitUntil(() => document.activeElement === screen.getAllByTestId("cite-pill")[0]);
  });
  it("opens the same source from its chip and restores focus to the chip", async () => {
    await open(); fireEvent.click(screen.getAllByTestId("source-chip")[0]!); await waitUntil(() => screen.queryByTestId("source-passage")); expect(screen.getByTestId("source-passage")).toHaveTextContent("First saved passage");
    fireEvent.click(screen.getByTestId("source-close")); await waitUntil(() => document.activeElement === screen.getAllByTestId("source-chip")[0]);
  });
  it("keeps sources for stopped answers", async () => { await open({ finish: "stopped" }); expect(screen.getAllByTestId("source-chip")).toHaveLength(2); expect(screen.queryByTestId("feedback-up")).toBeNull(); });
  it.each([{ finish: "failed" }, { finish: "stopped" }, { empty: true }])("omits feedback for ineligible answers %j", async (over) => { await open(over); expect(screen.queryByTestId("feedback-up")).toBeNull(); expect(screen.queryByTestId("feedback-down")).toBeNull(); });
  it("does not give the opening greeting feedback", async () => {
    const view = render(<QueryClientProvider client={context.client}><MessageItem assistant={toAssistantDetail(assistantRow())} message={toMessage(messageRow())} /></QueryClientProvider>);
    expect(view.container.querySelector('[data-testid="feedback-up"]')).toBeNull();
  });
  it("saves and clears a good-answer rating without optimistic updates", async () => {
    await open(); let release = () => {}; context.server.holds[`POST /api/v1/chats/${A}/sessions/${S}/messages/${M}/feedback`] = new Promise<void>((resolve) => { release = resolve; });
    fireEvent.click(screen.getByTestId("feedback-up")); expect(screen.getByTestId("feedback-up")).toHaveAttribute("aria-pressed", "false"); expect(screen.getByTestId("feedback-up")).toHaveAttribute("aria-busy", "true");
    await act(async () => release()); await waitUntil(() => screen.queryByTestId("feedback-up")?.getAttribute("aria-pressed") === "true");
    fireEvent.click(screen.getByTestId("feedback-up")); await waitUntil(() => screen.queryByTestId("feedback-up")?.getAttribute("aria-pressed") === "false");
  });
  it("saves a bad-answer rating", async () => { await open(); fireEvent.click(screen.getByTestId("feedback-down")); await waitUntil(() => screen.queryByTestId("feedback-down")?.getAttribute("aria-pressed") === "true"); });
  it("reports a feedback failure with fixed copy", async () => {
    context.server.forced[`POST /api/v1/chats/${A}/sessions/${S}/messages/${M}/feedback`] = { status: 502, message: "Hostile server sentence" }; await open(); fireEvent.click(screen.getByTestId("feedback-up"));
    await waitUntil(() => vi.mocked(notifyError).mock.calls.length > 0); expect(notifyError).toHaveBeenCalledWith(expect.objectContaining({ title: "The feedback wasn't saved. Try again." })); expect(screen.getByTestId("feedback-up")).toHaveAttribute("aria-pressed", "false");
  });
  it("guards repeated feedback while the request is held", async () => {
    let release = () => {}; const onChange = vi.fn(() => new Promise<void>((resolve) => { release = resolve; })); render(<FeedbackButtons messageId={M} value={null} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("feedback-up")); fireEvent.click(screen.getByTestId("feedback-down")); expect(onChange).toHaveBeenCalledOnce(); await act(async () => release());
  });
  it("orders pills and code copy before chips and thumbs", async () => {
    await open({ content: "First ##0$$ Fourth ##3$$\n\n```js\nconst value = 1;\n```" });
    const buttons = within(screen.getByTestId("message-assistant")).getAllByRole("button").map((button) => button.dataset.testid);
    expect(buttons).toEqual(["cite-pill", "cite-pill", "code-copy", "source-chip", "source-chip", "feedback-up", "feedback-down"]);
  });
  it("closes the source when another assistant is selected", async () => {
    const { router } = await open(); fireEvent.click(screen.getAllByTestId("cite-pill")[0]!); await waitUntil(() => screen.queryByTestId("source-passage"));
    await act(async () => router.navigate(`/chats?chat=${B}`)); await waitUntil(() => !screen.queryByTestId("source-drawer"));
  });
  it("keeps a sparse source selected by index across a message refetch", async () => {
    await open(); fireEvent.click(screen.getAllByTestId("cite-pill")[1]!); await waitUntil(() => screen.queryByTestId("source-passage")); expect(screen.getByTestId("source-passage")).toHaveTextContent("Fourth saved passage");
    setMessages(context.server, S, [messageRow(1, { content: "First ##0$$ Fourth ##3$$", reference: { ...reference, chunks: [...reference.chunks].reverse() } })]);
    await act(async () => { await context.client.invalidateQueries({ queryKey: chatRoot("t1") }); });
    expect(screen.getByTestId("source-title")).toHaveTextContent("Source 4"); expect(screen.getByTestId("source-passage")).toHaveTextContent("Fourth saved passage");
  });
  it("closes an open source if a fresh read redacts it", async () => {
    await open(); fireEvent.click(screen.getAllByTestId("cite-pill")[0]!); await waitUntil(() => screen.queryByTestId("source-passage"));
    setMessages(context.server, S, [messageRow(1, { content: "First ##0$$", reference: { chunks: [{ index: 0, unavailable: true }], doc_aggs: [] } })]);
    await act(async () => { await context.client.invalidateQueries({ queryKey: chatRoot("t1") }); });
    await waitUntil(() => !screen.queryByTestId("source-drawer")); expect(screen.getByTestId("cite-pill-unavailable")).toBeInTheDocument();
  });
  it("does not move passage focus when a streaming answer finishes", async () => {
    await open(); const peer = streamOf([{ code: 0, data: { answer: "New partial", session_id: S, message_id: "f".repeat(32) } }, { code: 0, data: { answer: "New final", session_id: S, message_id: "f".repeat(32), final: true } }], { holdAfter: 1 }); vi.stubGlobal("fetch", peer);
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Another question" } }); fireEvent.click(screen.getByTestId("chat-send")); await waitUntil(() => screen.queryByText("New partial"));
    fireEvent.click(screen.getAllByTestId("cite-pill")[0]!); await waitUntil(() => screen.queryByTestId("source-passage")); await act(async () => peer.release());
    expect(screen.getByTestId("source-passage")).toHaveFocus();
  });
});
