import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { A, B, S, chatSetup } from "@/test/chat-page";
import { DATASET_ID, datasetRow } from "@/test/dataset-server";
import { assistantRow, setAssistants } from "@/test/server-areas/assistants";
import { messageRow, setMessages, streamOf } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";

describe("streaming conversation", () => {
  const adapter = http.defaults.adapter; let context: ReturnType<typeof chatSetup>;
  const M = messageRow().id;
  const frame = (data: object, code = 0) => ({ code, message: "", data: { session_id: S, message_id: M, ...data } });
  beforeEach(() => { context = chatSetup(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useWorkspaceStore.getState().reset(); useUserStore.getState().reset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  async function open(peer: ReturnType<typeof streamOf>, draft = false) {
    vi.stubGlobal("fetch", peer); const view = context.mount(`/chats?chat=${A}${draft ? "" : `&session=${S}`}`);
    await waitUntil(() => screen.queryByTestId("chat-input")); return view;
  }
  const send = (text = "Question") => { fireEvent.change(screen.getByTestId("chat-input"), { target: { value: text } }); fireEvent.click(screen.getByTestId("chat-send")); };
  const readyText = (text: string) => waitUntil(() => screen.queryByTestId("message-assistant")?.textContent?.includes(text));
  const held = (answer = "Partial") => streamOf([frame({ answer })], { hold: true });
  it("appends deltas and replaces them with the final canonical answer", async () => {
    const peer = streamOf([frame({ answer: "First " }), frame({ answer: "second" }), frame({ answer: "Canonical answer", final: true, finish: "complete" })], { holdAfter: 1 }); await open(peer); send(); await readyText("First");
    await act(async () => peer.release()); await readyText("Canonical answer"); expect(screen.getByTestId("message-assistant")).not.toHaveTextContent("First second");
  });
  it("never flashes a split marker and adds the final citation pill", async () => {
    const peer = streamOf([frame({ answer: "Fact ##" }), frame({ answer: "1$$" }), frame({ answer: "Fact ##1$$", final: true, reference: { chunks: [{ index: 1, doc_name: "facts.pdf" }], doc_aggs: [] } })], { holdAfter: 1 });
    await open(peer); send(); await readyText("Fact"); expect(screen.getByTestId("message-assistant")).not.toHaveTextContent("##"); await act(async () => peer.release()); await waitUntil(() => screen.queryByTestId("cite-pill")); expect(screen.getByTestId("cite-pill")).toHaveAccessibleName("Source 2: facts.pdf"); expect(screen.getByTestId("message-assistant")).not.toHaveTextContent("##");
  });
  it("hides complete markers until the final reference arrives", async () => {
    const peer = held("Fact ##1$$"); await open(peer); send(); await readyText("Fact"); expect(screen.getByTestId("message-assistant")).not.toHaveTextContent("##"); expect(screen.queryByTestId("cite-pill")).toBeNull();
  });
  it("retains partial text after an error frame", async () => {
    const peer = streamOf([frame({ answer: "Kept partial" }), frame({ reason: "rerank_unavailable", final: true }, 502)]); await open(peer); send(); await waitUntil(() => screen.queryByTestId("message-failed")); expect(screen.getByTestId("message-assistant")).toHaveTextContent("Kept partial");
  });
  it("stops, refetches and replaces the local partial with saved stopped text", async () => {
    const peer = held(); await open(peer); send(); await readyText("Partial"); const before = context.server.callsTo("GET", `/api/v1/chats/${A}/sessions/${S}`).length;
    setMessages(context.server, S, [messageRow(1, { content: "Authoritative saved partial", finish: "stopped" })]); fireEvent.click(screen.getByTestId("chat-stop"));
    await waitUntil(() => context.server.callsTo("GET", `/api/v1/chats/${A}/sessions/${S}`).length > before); await readyText("Authoritative saved partial"); expect(screen.getAllByTestId("message-assistant")).toHaveLength(1); expect(screen.getByTestId("message-stopped")).toBeInTheDocument();
  });
  it("shows the stopped line when stopped before the first token", async () => {
    const peer = streamOf([], { hold: true }); await open(peer); send(); await waitUntil(() => screen.queryByTestId("chat-stop")); fireEvent.click(screen.getByTestId("chat-stop")); await waitUntil(() => screen.queryByTestId("message-stopped")); expect(screen.queryByTestId("message-generating")).toBeNull();
  });
  it("restores the exact draft and adds no messages after a pre-stream refusal", async () => {
    await open(streamOf([], { status: 409, reason: "turn_in_progress" })); send("  Original question  "); await waitUntil(() => screen.queryByTestId("chat-send-error")); expect(screen.getByTestId("chat-input")).toHaveValue("  Original question  "); expect(screen.queryByTestId("message-assistant")).toBeNull(); expect(screen.queryByTestId("message-user")).toBeNull();
  });
  it("focuses the textarea after a completed turn", async () => {
    await open(streamOf([frame({ answer: "Finished", final: true })])); send(); await readyText("Finished"); await waitUntil(() => screen.queryByTestId("chat-send")); expect(screen.getByTestId("chat-input")).toHaveFocus(); expect(screen.getByTestId("chat-input")).not.toHaveAttribute("readonly");
  });
  it("writes a draft's new session with replace without aborting its held stream", async () => {
    const peer = held(); const { router } = await open(peer, true); send(); await readyText("Partial"); await waitUntil(() => router.state.location.search.includes(S)); expect(router.state.historyAction).toBe("REPLACE"); expect(peer.calls[0]?.init?.signal?.aborted).toBe(false);
  });
  it("announces start then finish without announcing each delta", async () => {
    const peer = streamOf([frame({ answer: "First" }), frame({ answer: "Final", final: true })], { holdAfter: 1 }); await open(peer); send(); await waitUntil(() => screen.queryByTestId("chat-live")?.textContent === "Answer started"); await act(async () => peer.release()); await waitUntil(() => screen.queryByTestId("chat-live")?.textContent === "Answer finished");
  });
  it("announces a stopped answer", async () => { await open(held()); send(); await readyText("Partial"); fireEvent.click(screen.getByTestId("chat-stop")); await waitUntil(() => screen.queryByTestId("chat-live")?.textContent === "Answer stopped"); });
  it("announces a failed answer", async () => { await open(streamOf([frame({ answer: "Partial" }), frame({ reason: "provider_timeout" }, 502)])); send(); await waitUntil(() => screen.queryByTestId("chat-live")?.textContent === "The answer couldn't be completed"); });
  it("shows retrieval activity before a sourced answer begins", async () => {
    context.server.datasets[DATASET_ID] = datasetRow(); setAssistants(context.server, [assistantRow(1, { kb_ids: [DATASET_ID] })]); await open(streamOf([], { hold: true })); send(); await waitUntil(() => screen.queryByTestId("message-generating")); expect(screen.getByTestId("message-generating")).toHaveTextContent("Looking through your documents");
  });
  it("shows Thinking for plain chat", async () => { await open(streamOf([], { hold: true })); send(); await waitUntil(() => screen.queryByTestId("message-generating")); expect(screen.getByTestId("message-generating")).toHaveTextContent("Thinking"); });
  it("keeps the textarea readOnly and focused while streaming", async () => { await open(held()); send(); await readyText("Partial"); expect(screen.getByTestId("chat-input")).toHaveAttribute("readonly"); expect(screen.getByTestId("chat-input")).not.toBeDisabled(); expect(screen.getByTestId("chat-input")).toHaveFocus(); });
  it("sends once for a repeated click", async () => { const peer = held(); await open(peer); const button = screen.getByTestId("chat-send"); send(); fireEvent.click(button); await waitUntil(() => peer.calls.length === 1); expect(peer.calls).toHaveLength(1); });
  it("aborts and clears the local turn when New chat is selected", async () => {
    const peer = held(); await open(peer); send(); await readyText("Partial"); fireEvent.click(screen.getByTestId("rail-chat-new")); await waitUntil(() => peer.calls[0]?.init?.signal?.aborted); expect(screen.queryByTestId("message-assistant")).toBeNull();
  });
  it("aborts when another assistant is selected", async () => {
    const peer = held(); const { router } = await open(peer); send(); await readyText("Partial"); fireEvent.click(screen.getAllByTestId("rail-assistant-row")[1]!); await waitUntil(() => peer.calls[0]?.init?.signal?.aborted); expect(router.state.location.search).toBe(`?chat=${B}`);
  });
  it("shows the empty-response badge on a final empty result", async () => { await open(streamOf([frame({ answer: "No matching passages", final: true, empty: true })])); send(); await waitUntil(() => screen.queryByTestId("message-empty-badge")); });
  it("uses the saved complete message once reconciliation finishes", async () => {
    const peer = streamOf([frame({ answer: "Partial" }), frame({ answer: "Final", final: true })], { holdAfter: 1 }); await open(peer); send(); await readyText("Partial"); setMessages(context.server, S, [messageRow(1, { content: "Saved final", finish: "complete" })]); await act(async () => peer.release()); await readyText("Saved final"); expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
  });
  function metrics(log: HTMLElement, top: number) {
    Object.defineProperties(log, { scrollHeight: { configurable: true, value: 1200 }, clientHeight: { configurable: true, value: 400 }, scrollTop: { configurable: true, writable: true, value: top }, scrollTo: { configurable: true, value: vi.fn((options: ScrollToOptions) => { log.scrollTop = options.top ?? 0; }) } });
    fireEvent.scroll(log); return vi.mocked(log.scrollTo);
  }
  it("follows new deltas when the reader is at the bottom", async () => {
    const peer = streamOf([frame({ answer: "First" }), frame({ answer: "Final", final: true })], { holdAfter: 1 }); await open(peer); const log = screen.getByRole("log"); const scroll = metrics(log, 800); send(); await readyText("First"); scroll.mockClear(); await act(async () => peer.release()); await readyText("Final"); expect(scroll).toHaveBeenCalled();
  });
  it("does not follow when the reader has scrolled up", async () => {
    const peer = streamOf([frame({ answer: "First" }), frame({ answer: "Final", final: true })], { holdAfter: 1 }); await open(peer); send(); await readyText("First"); const log = screen.getByRole("log"), scroll = metrics(log, 100); scroll.mockClear(); await act(async () => peer.release()); await readyText("Final"); expect(scroll).not.toHaveBeenCalled(); expect(screen.getByTestId("message-jump")).toBeInTheDocument();
  });
  it("jumps to the latest message on request", async () => {
    await open(held()); send(); await readyText("Partial"); const scroll = metrics(screen.getByRole("log"), 100); fireEvent.click(screen.getByTestId("message-jump")); expect(scroll).toHaveBeenCalledWith(expect.objectContaining({ top: 1200 })); expect(screen.queryByTestId("message-jump")).toBeNull();
  });
  it("sending always scrolls to the end", async () => { await open(held()); const scroll = metrics(screen.getByRole("log"), 100); send(); await readyText("Partial"); expect(scroll).toHaveBeenCalledWith(expect.objectContaining({ top: 1200 })); });
  it("uses instant scrolling for reduced motion", async () => {
    await open(held()); send(); await readyText("Partial"); vi.stubGlobal("matchMedia", (media: string) => ({ matches: media.includes("prefers-reduced-motion"), media, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const scroll = metrics(screen.getByRole("log"), 100); fireEvent.click(screen.getByTestId("message-jump")); expect(scroll).toHaveBeenLastCalledWith(expect.objectContaining({ behavior: "auto" }));
  });
  it("keeps Send guarded between the final answer and DONE", async () => {
    const peer = streamOf([frame({ answer: "Final before DONE", final: true })], { hold: true }); await open(peer); send(); await readyText("Final before DONE");
    expect(screen.getByTestId("chat-input")).toHaveAttribute("readonly"); expect(screen.getByTestId("chat-stop")).toBeInTheDocument();
    await act(async () => peer.release()); await waitUntil(() => screen.queryByTestId("chat-send")); expect(screen.getByTestId("chat-input")).not.toHaveAttribute("readonly"); expect(peer.calls).toHaveLength(1);
  });
  it("keeps partial text and fixed failure copy when the stream connection fails", async () => {
    let controller: ReadableStreamDefaultController<Uint8Array>;
    const peer = streamOf([]); await open(peer);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream<Uint8Array>({ start(value) { controller = value; controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(frame({ answer: "Saved locally" }))}\n\n`)); } }), { headers: { "content-type": "text/event-stream" } })));
    send(); await readyText("Saved locally"); await act(async () => controller.error(new Error("Hostile transport sentence")));
    await waitUntil(() => screen.queryByTestId("message-failed")); expect(screen.getByTestId("message-assistant")).toHaveTextContent("Saved locally"); expect(screen.getByTestId("message-assistant")).not.toHaveTextContent("Hostile transport sentence");
  });
  it("restores the same draft after two successive refusals", async () => {
    const peer = streamOf([], { status: 409, reason: "turn_in_progress" }); await open(peer); send("Repeat question"); await waitUntil(() => screen.queryByTestId("chat-input")?.getAttribute("readonly") === null && screen.queryByTestId("chat-send-error"));
    fireEvent.click(screen.getByTestId("chat-send")); await waitUntil(() => peer.calls.length === 2 && (screen.getByTestId("chat-input") as HTMLTextAreaElement).value === "Repeat question"); expect(screen.queryByTestId("message-user")).toBeNull();
  });
});
