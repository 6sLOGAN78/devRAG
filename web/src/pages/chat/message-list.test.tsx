import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toAssistantDetail, toMessage, toSessionDetail } from "@/services/chat-service";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { S, chatSetup } from "@/test/chat-page";
import { assistantRow } from "@/test/server-areas/assistants";
import { messageRow, sessionRow, setMessages } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";
import { MessageItem } from "./message-item";
import { MessageList } from "./message-list";

describe("stored chat messages", () => {
  const adapter = http.defaults.adapter; let context: ReturnType<typeof chatSetup>;
  beforeEach(() => { context = chatSetup(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  const assistant = () => toAssistantDetail(assistantRow(1, { prompt_config: { system: "", prologue: "Hello from the assistant", empty_response: "No matches" } }));
  function item(over = {}) { return render(<MessageItem assistant={assistant()} message={toMessage(messageRow(1, over))} />); }
  it("renders user text literally", () => { item({ role: "user", content: "<img src=x onerror=alert(1)>" }); expect(screen.getByTestId("message-user")).toHaveTextContent("<img src=x onerror=alert(1)>"); expect(screen.getByTestId("message-user").querySelector("img")).toBeNull(); });
  it("renders completed answer text and measured metadata", () => { item({ content: "Saved answer", latency_ms: 1240 }); expect(screen.getByTestId("message-assistant")).toHaveAttribute("data-finish", "complete"); expect(screen.getByTestId("message-latency")).toHaveTextContent("1.2 s"); expect(screen.getByTestId("message-tokens")).toHaveTextContent("Tokens: 10"); });
  it("renders a stopped answer and estimated token count", () => { item({ finish: "stopped", usage: { input: 4, output: 3, total: 7, estimated: true } }); expect(screen.getByTestId("message-stopped")).toHaveTextContent("This answer was stopped before it finished."); expect(screen.getByTestId("message-tokens")).toHaveTextContent("Tokens: about 7"); });
  it("renders only the stopped line when stopped before any text", () => { item({ content: "", finish: "stopped" }); expect(screen.getByTestId("message-stopped")).toBeInTheDocument(); expect(screen.queryByTestId("message-meta")).toBeNull(); expect(screen.queryByTestId("message-failed")).toBeNull(); });
  it("renders a failed line without completion metadata", () => { item({ finish: "failed", content: "Partial answer" }); expect(screen.getByTestId("message-failed")).toHaveTextContent("The answer couldn't be completed. Ask the question again."); expect(screen.queryByTestId("message-meta")).toBeNull(); });
  it("labels an empty retrieval result", () => { item({ empty: true, content: "No matching passages" }); expect(screen.getByTestId("message-empty-badge")).toHaveTextContent("No sources found"); });
  it("resolves sparse citations by their stored index", () => {
    item({ content: "First ##0$$ Fourth ##3$$", reference: { chunks: [{ index: 0, doc_name: "first.pdf" }, { index: 3, doc_name: "fourth.pdf" }], doc_aggs: [] } });
    expect(screen.getAllByTestId("cite-pill")[1]).toHaveAccessibleName("Source 4: fourth.pdf"); expect(screen.getAllByTestId("cite-pill")[1]).toHaveAttribute("data-cite-index", "3"); expect(screen.getAllByTestId("cite-pill")).toHaveLength(2);
  });
  it("escapes hostile saved answer markup", () => { const { container } = item({ content: "<script>alert(1)</script>" }); expect(container.querySelector("script")).toBeNull(); expect(container).toHaveTextContent("<script>alert(1)</script>"); });
  function list(over: Partial<Parameters<typeof MessageList>[0]> = {}) {
    return render(<MemoryRouter><QueryClientProvider client={context.client}><MessageList assistant={assistant()} {...over} /></QueryClientProvider></MemoryRouter>);
  }
  it("starts the conversation with the derived greeting without metadata", () => { list(); expect(screen.getByRole("log", { name: "Conversation" })).toHaveAttribute("aria-live", "off"); expect(screen.getByTestId("message-greeting")).toHaveTextContent("Hello from the assistant"); expect(screen.queryByTestId("message-meta")).toBeNull(); });
  it("shows the draft hint when the greeting is empty", () => { const a = assistant(); a.promptConfig.prologue = ""; list({ assistant: a }); expect(screen.getByTestId("chat-draft")).toHaveTextContent("Ask a question."); });
  it("renders loading skeletons and an in-list retry state", () => {
    const onRetry = vi.fn(); const view = list({ loading: true }); expect(screen.getByTestId("message-skeleton")).toBeInTheDocument(); view.unmount();
    list({ error: true, onRetry }); fireEvent.click(screen.getByRole("button", { name: "Try again" })); expect(onRetry).toHaveBeenCalledOnce();
  });
  it("loads earlier messages before the latest fifty and retains the scroll anchor", async () => {
    const all = Array.from({ length: 75 }, (_, index) => messageRow(index + 1)); setMessages(context.server, S, all);
    const session = toSessionDetail({ ...sessionRow(), messages: all.slice(25), has_earlier: true }); list({ session, sessionId: S });
    const log = screen.getByRole("log"), first = screen.getAllByTestId("message-assistant")[0]!; log.scrollTop = 100;
    vi.spyOn(first, "getBoundingClientRect").mockReturnValueOnce({ top: 100 } as DOMRect).mockReturnValue({ top: 340 } as DOMRect);
    fireEvent.click(screen.getByTestId("message-load-earlier")); await waitUntil(() => screen.queryAllByTestId("message-assistant").length === 75);
    expect(log.scrollTop).toBe(340); expect(screen.getAllByTestId("message-assistant")[0]).toHaveTextContent("Answer 1"); expect(screen.queryByTestId("message-load-earlier")).toBeNull();
  });
  it("keeps the latest page visible if an earlier page fails", async () => {
    const all = Array.from({ length: 51 }, (_, index) => messageRow(index + 1)); setMessages(context.server, S, all);
    context.server.forced[`GET /api/v1/chats/${assistant().id}/sessions/${S}`] = { status: 502, message: "failure" };
    list({ session: toSessionDetail({ ...sessionRow(), messages: all.slice(1), has_earlier: true }), sessionId: S }); fireEvent.click(screen.getByTestId("message-load-earlier"));
    await waitUntil(() => screen.queryByText("Couldn't load this chat.")); expect(screen.getAllByTestId("message-assistant")).toHaveLength(50);
  });
});
