import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/services/http";
import { notifySuccess } from "@/services/notify";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUserStore } from "@/stores/user-store";
import { A, B, S, chatSetup, chatUser } from "@/test/chat-page";
import { assistantRow, setAssistants, setMembersWithChats } from "@/test/server-areas/assistants";
import { messageRow, setMessages } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";

vi.mock("@/services/notify", () => ({ notifySuccess: vi.fn(), notifyError: vi.fn() }));
describe("ChatPage shell", () => {
  const adapter = http.defaults.adapter; let context: ReturnType<typeof chatSetup>;
  beforeEach(() => { context = chatSetup(); vi.mocked(notifySuccess).mockClear(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useWorkspaceStore.getState().reset(); useUserStore.getState().reset(); vi.unstubAllGlobals(); });
  const ready = () => waitUntil(() => screen.queryAllByTestId("rail-assistant-row").length > 0);
  it("keeps the requested assistant and session while the signed-in workspace first initializes", async () => {
    useWorkspaceStore.getState().reset(); useUserStore.getState().reset();
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`);
    act(() => { useUserStore.getState().setUser(chatUser); useWorkspaceStore.getState().initialise("u1", "t1", []); });
    await ready();
    await waitUntil(() => screen.queryByTestId("chat-input"));
    expect(new URLSearchParams(router.state.location.search).get("chat")).toBe(A);
    expect(new URLSearchParams(router.state.location.search).get("session")).toBe(S);
  });
  it("opens the create dialog from the empty state and restores focus", async () => {
    setAssistants(context.server, []); context.mount(); await waitUntil(() => screen.queryByTestId("chat-empty-create"));
    const opener = screen.getByTestId("chat-empty-create"); fireEvent.click(opener); await waitUntil(() => screen.queryByTestId("field-assistant-name"));
    fireEvent.click(screen.getByTestId("assistant-close")); await waitUntil(() => document.activeElement === opener);
  });
  it("selects a newly created assistant as a draft", async () => {
    setAssistants(context.server, []); const { router } = context.mount(); await waitUntil(() => screen.queryByTestId("chat-empty-create"));
    fireEvent.click(screen.getByTestId("chat-empty-create")); await waitUntil(() => screen.queryByTestId("field-assistant-name"));
    fireEvent.change(screen.getByTestId("field-assistant-name"), { target: { value: "New helper" } }); fireEvent.click(screen.getByTestId("assistant-submit"));
    await waitUntil(() => !screen.queryByRole("dialog") && router.state.location.search.includes("chat="));
    expect(new URLSearchParams(router.state.location.search).has("session")).toBe(false);
    await waitUntil(() => screen.queryByTestId("message-greeting"));
  });
  it("opens the same create dialog from the rail", async () => {
    context.mount(); await ready(); fireEvent.click(screen.getByTestId("rail-assistant-new"));
    await waitUntil(() => screen.queryByTestId("field-assistant-name")); expect(screen.getByTestId("assistant-dialog")).toBeInTheDocument();
  });
  it("clears a gone assistant and selects the first available one", async () => {
    const gone = "f".repeat(32); const { router } = context.mount(`/chats?chat=${gone}&session=${S}`);
    await waitUntil(() => vi.mocked(notifySuccess).mock.calls.some(([text]) => text === "That assistant no longer exists."));
    await waitUntil(() => router.state.location.search === `?chat=${A}`); expect(router.state.historyAction).toBe("REPLACE");
  });
  it("clears only a gone chat and keeps the assistant", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${"f".repeat(32)}`);
    await waitUntil(() => vi.mocked(notifySuccess).mock.calls.some(([text]) => text === "That chat no longer exists."));
    expect(router.state.location.search).toBe(`?chat=${A}`); expect(router.state.historyAction).toBe("REPLACE");
  });
  it("offers an in-place retry for an assistant failure and keeps the rail", async () => {
    context.server.forced[`GET /api/v1/chats/${A}`] = { status: 502, message: "failure" }; context.mount(`/chats?chat=${A}`);
    await waitUntil(() => screen.queryByText("Couldn't load this assistant")); expect(screen.getByTestId("chat-rail")).toBeInTheDocument();
    delete context.server.forced[`GET /api/v1/chats/${A}`]; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await waitUntil(() => screen.queryByTestId("chat-draft"));
  });
  it("keeps a stored-chat load failure separate from the assistant", async () => {
    context.server.forced[`GET /api/v1/chats/${A}/sessions/${S}`] = { status: 502, message: "failure" }; context.mount(`/chats?chat=${A}&session=${S}`);
    await waitUntil(() => screen.queryByText("Couldn't load this chat.")); expect(screen.getAllByTestId("rail-assistant-row")).toHaveLength(2);
  });
  it("opens a left sheet on a narrow screen and closes it on assistant selection", async () => {
    vi.stubGlobal("matchMedia", (media: string) => ({ matches: false, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const { router } = context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("rail-open"));
    fireEvent.click(screen.getByTestId("rail-open")); await ready(); expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId("rail-assistant-row")[1]!); await waitUntil(() => router.state.location.search === `?chat=${B}`);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("clears both parameters on a workspace switch before any old-id request in the new workspace", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`); await ready();
    const before = context.server.callsTo("GET", `/api/v1/chats/${A}`).length;
    act(() => { useUserStore.getState().setUser({ ...chatUser, tenantId: "t2" }); useWorkspaceStore.getState().initialise("u1", "t2", []); });
    await waitUntil(() => router.state.location.search === "");
    expect(context.server.callsTo("GET", `/api/v1/chats/${A}`)).toHaveLength(before); expect(screen.queryByTestId("chat-draft")).toBeNull();
  });
  it("sets the document title and fixed-height page structure", async () => {
    context.mount(); await ready(); expect(document.title).toBe("Chat - devRag");
    expect(screen.getByTestId("chat-page")).toHaveClass("h-[calc(100dvh-8rem)]", "min-h-[480px]");
  });
  it("closes the mobile rail before opening the assistant dialog", async () => {
    vi.stubGlobal("matchMedia", (media: string) => ({ matches: false, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    context.mount(); fireEvent.click(screen.getByTestId("rail-open")); await ready(); fireEvent.click(screen.getByTestId("rail-assistant-new"));
    await waitUntil(() => screen.queryByTestId("field-assistant-name")); expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.queryByTestId("chat-rail")).toBeNull(); expect(screen.getByTestId("field-assistant-name")).toHaveFocus();
    fireEvent.click(screen.getByTestId("assistant-close")); await waitUntil(() => document.activeElement === screen.getByTestId("rail-open"));
  });
  it("loads a saved stopped turn when both URL parameters are restored", async () => {
    setMessages(context.server, S, [messageRow(1, { content: "Saved partial answer", finish: "stopped" })]);
    const first = context.mount(`/chats?chat=${A}&session=${S}`); await waitUntil(() => screen.queryByTestId("message-stopped")); expect(screen.getByTestId("message-assistant")).toHaveTextContent("Saved partial answer");
    first.unmount(); context.mount(`/chats?chat=${A}&session=${S}`); await waitUntil(() => screen.queryByTestId("message-stopped")); expect(screen.getByTestId("message-assistant")).toHaveTextContent("Saved partial answer");
  });
  it("shows the derived greeting before saved messages", async () => {
    setAssistants(context.server, [assistantRow(1, { prompt_config: { system: "", prologue: "Welcome back", empty_response: "No matches" } })]);
    setMessages(context.server, S, [messageRow()]); context.mount(`/chats?chat=${A}&session=${S}`); await waitUntil(() => screen.queryByTestId("message-assistant"));
    expect(screen.getByTestId("message-greeting").compareDocumentPosition(screen.getByTestId("message-assistant")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  const menu = async (target: string) => {
    fireEvent.pointerDown(screen.getByTestId("chat-more"), { button: 0, ctrlKey: false }); await waitUntil(() => screen.queryByTestId(target)); fireEvent.click(screen.getByTestId(target));
  };
  it("deletes a stored chat from the header and returns to draft", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`); await waitUntil(() => screen.queryByTestId("chat-more"));
    await menu("chat-menu-delete-chat"); await waitUntil(() => screen.queryByTestId("delete-chat-confirm")); fireEvent.click(screen.getByTestId("delete-chat-confirm"));
    await waitUntil(() => router.state.location.search === `?chat=${A}`); expect(screen.queryByRole("alertdialog")).toBeNull(); expect(screen.getByTestId("chat-draft")).toBeInTheDocument();
  });
  it("refetches the team count before deleting an assistant and selects another", async () => {
    setAssistants(context.server, [assistantRow(1, { permission: "team" }), assistantRow(2)]); setMembersWithChats(context.server, A, 2);
    const { router } = context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("chat-more")); await menu("chat-menu-delete-assistant");
    await waitUntil(() => { const button = screen.queryByTestId("delete-assistant-confirm"); return button && button.getAttribute("aria-disabled") !== "true"; }); expect(screen.getByTestId("delete-assistant-body")).toHaveTextContent("2 other members");
    fireEvent.click(screen.getByTestId("delete-assistant-confirm")); await waitUntil(() => router.state.location.search === `?chat=${B}`); expect(screen.queryByRole("alertdialog")).toBeNull();
  });
  it("opens settings from the header and restores focus to Settings", async () => {
    context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("chat-settings")); const trigger = screen.getByTestId("chat-settings"); fireEvent.click(trigger);
    await waitUntil(() => screen.queryByTestId("field-assistant-name")); expect(screen.getByTestId("field-assistant-name")).toHaveValue("Assistant 1"); fireEvent.click(screen.getByTestId("assistant-close")); await waitUntil(() => document.activeElement === trigger);
  });
  it("returns confirmation focus to the header menu", async () => {
    context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("chat-more")); const trigger = screen.getByTestId("chat-more"); await menu("chat-menu-delete-assistant");
    await waitUntil(() => screen.queryByTestId("delete-assistant-keep")); expect(screen.queryByRole("dialog")).toBeNull(); fireEvent.click(screen.getByTestId("delete-assistant-keep")); await waitUntil(() => document.activeElement === trigger);
  });
  it("lets a non-creator manager narrow sharing before selecting another assistant", async () => {
    setAssistants(context.server, [assistantRow(1, { permission: "team", created_by: "other" }), assistantRow(2)]);
    const { router } = context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("chat-settings")); fireEvent.click(screen.getByTestId("chat-settings"));
    await waitUntil(() => screen.queryByTestId("field-assistant-name")); fireEvent.click(screen.getByTestId("assistant-visibility-me")); fireEvent.click(screen.getByTestId("assistant-submit"));
    await waitUntil(() => router.state.location.search === `?chat=${B}`); expect(notifySuccess).toHaveBeenCalledWith("Assistant saved. Only the person who made it can see it now."); expect(screen.queryByRole("dialog")).toBeNull();
  });
});
