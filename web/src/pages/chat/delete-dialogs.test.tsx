import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { assistantKey } from "@/hooks/use-chat-request";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { toAssistantDetail, toSession } from "@/services/chat-service";
import { http } from "@/services/http";
import { notifyError, notifySuccess } from "@/services/notify";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { A, S, chatSetup } from "@/test/chat-page";
import { assistantRow, setMembersWithChats } from "@/test/server-areas/assistants";
import { membershipRow, storedMemberships } from "@/test/dataset-server";
import { sessionRow } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";
import { ConversationHeader } from "./conversation-header";
import { DeleteAssistantDialog, DeleteChatDialog } from "./delete-dialogs";

vi.mock("@/services/notify", () => ({ notifySuccess: vi.fn(), notifyError: vi.fn() }));
describe("chat header and confirmations", () => {
  let context: ReturnType<typeof chatSetup>; const adapter = http.defaults.adapter;
  beforeEach(() => { context = chatSetup(); vi.mocked(notifySuccess).mockClear(); vi.mocked(notifyError).mockClear(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); vi.unstubAllGlobals(); });
  const detail = (over = {}) => toAssistantDetail(assistantRow(1, over));
  function mount(kind: "assistant" | "chat", over = {}) {
    const onDeleted = vi.fn(), onOpenChange = vi.fn(), assistant = detail(over);
    context.client.setQueryData(assistantKey("t1", A), assistant);
    return { ...render(<MemoryRouter><QueryClientProvider client={context.client}>{kind === "assistant"
      ? <DeleteAssistantDialog assistant={assistant} open onOpenChange={onOpenChange} onDeleted={onDeleted} />
      : <DeleteChatDialog chatId={A} session={toSession(sessionRow())} open onOpenChange={onOpenChange} onDeleted={onDeleted} />}</QueryClientProvider></MemoryRouter>), onDeleted, onOpenChange };
  }
  const ready = () => waitUntil(() => screen.queryByTestId("delete-assistant-confirm")?.getAttribute("aria-disabled") !== "true");
  it("focuses Keep assistant by default", async () => { mount("assistant"); await ready(); expect(screen.getByTestId("delete-assistant-keep")).toHaveFocus(); });
  it("uses the plain confirmation at count zero", async () => { mount("assistant"); await ready(); expect(screen.getByTestId("delete-assistant-body")).toHaveAttribute("data-count", "0"); expect(screen.getByTestId("delete-assistant-body")).not.toHaveTextContent("other members"); });
  it("refreshes and displays the count of other members", async () => { setMembersWithChats(context.server, A, 2); mount("assistant", { permission: "team" }); await ready(); expect(screen.getByTestId("delete-assistant-body")).toHaveAttribute("data-count", "2"); expect(screen.getByTestId("delete-assistant-body")).toHaveTextContent("including the chats of 2 other members"); });
  it("blocks confirmation until its fresh count settles", async () => {
    let release = () => {}; context.server.holds[`GET /api/v1/chats/${A}`] = new Promise<void>((resolve) => { release = resolve; }); mount("assistant");
    expect(screen.getByTestId("delete-assistant-confirm")).toHaveAttribute("aria-disabled", "true"); expect(screen.getByTestId("delete-assistant-confirm")).toHaveAttribute("aria-busy", "true");
    fireEvent.click(screen.getByTestId("delete-assistant-confirm")); expect(context.server.callsTo("DELETE", `/api/v1/chats/${A}`)).toHaveLength(0);
    await act(async () => release()); await ready();
  });
  it("retains a cached count and permits deletion after a failed refresh", async () => {
    context.server.forced[`GET /api/v1/chats/${A}`] = { status: 502, message: "failure" }; mount("assistant", { permission: "team", members_with_chats: 3 } as never);
    await ready(); expect(screen.getByTestId("delete-assistant-body")).toHaveAttribute("data-count", "3");
  });
  it("closes when the refreshed assistant is gone", async () => { context.server.forced[`GET /api/v1/chats/${A}`] = { status: 404, message: "gone" }; const view = mount("assistant"); await waitUntil(() => view.onOpenChange.mock.calls.length > 0); expect(view.onOpenChange).toHaveBeenCalledWith(false); });
  it("deletes the assistant and reports success", async () => { const view = mount("assistant"); await ready(); fireEvent.click(screen.getByTestId("delete-assistant-confirm")); await waitUntil(() => view.onDeleted.mock.calls.length === 1); expect(notifySuccess).toHaveBeenCalledWith("Assistant deleted"); expect(view.onOpenChange).toHaveBeenCalledWith(false); });
  it("reports an assistant deletion failure without closing", async () => {
    context.server.forced[`DELETE /api/v1/chats/${A}`] = { status: 502, message: "failure" }; const view = mount("assistant"); await ready(); fireEvent.click(screen.getByTestId("delete-assistant-confirm"));
    await waitUntil(() => vi.mocked(notifyError).mock.calls.length > 0); expect(notifyError).toHaveBeenCalledWith(expect.objectContaining({ title: "The assistant wasn't deleted. Try again." })); expect(view.onDeleted).not.toHaveBeenCalled();
  });
  it("guards repeated confirms and Escape while deleting", async () => {
    let release = () => {}; context.server.holds[`DELETE /api/v1/chats/${A}`] = new Promise<void>((resolve) => { release = resolve; }); const view = mount("assistant"); await ready();
    fireEvent.click(screen.getByTestId("delete-assistant-confirm")); fireEvent.click(screen.getByTestId("delete-assistant-confirm")); await waitUntil(() => context.server.callsTo("DELETE", `/api/v1/chats/${A}`).length === 1);
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" }); fireEvent.click(screen.getByTestId("delete-assistant-keep")); expect(view.onOpenChange).not.toHaveBeenCalled(); await act(async () => release()); await waitUntil(() => view.onDeleted.mock.calls.length === 1);
  });
  it("focuses Keep chat by default", () => { mount("chat"); expect(screen.getByTestId("delete-chat-keep")).toHaveFocus(); });
  it("deletes only the selected chat", async () => { const view = mount("chat"); fireEvent.click(screen.getByTestId("delete-chat-confirm")); await waitUntil(() => view.onDeleted.mock.calls.length === 1); expect(context.server.callsTo("DELETE", `/api/v1/chats/${A}/sessions/${S}`)).toHaveLength(1); expect(notifySuccess).toHaveBeenCalledWith("Chat deleted"); });
  it("reports a chat deletion failure", async () => { context.server.forced[`DELETE /api/v1/chats/${A}/sessions/${S}`] = { status: 502, message: "failure" }; mount("chat"); fireEvent.click(screen.getByTestId("delete-chat-confirm")); await waitUntil(() => vi.mocked(notifyError).mock.calls.length > 0); expect(notifyError).toHaveBeenCalledWith(expect.objectContaining({ title: "The chat wasn't deleted. Try again." })); });
  function header(assistant = detail(), session = false) {
    return render(<MemoryRouter><QueryClientProvider client={context.client}><ConversationHeader assistant={assistant} session={session ? toSession(sessionRow()) : undefined} onSettings={vi.fn()} onDeleteChat={vi.fn()} onDeleteAssistant={vi.fn()} /></QueryClientProvider></MemoryRouter>);
  }
  it("shows settings and deletion for the creator", () => { header(); expect(screen.getByTestId("chat-settings")).toBeInTheDocument(); expect(screen.getByTestId("chat-more")).toBeInTheDocument(); });
  it("omits management and an empty menu for a member", () => {
    useUserStore.getState().setUser({ ...useUserStore.getState().user!, id: "member" });
    // The caller's own workspace remains owner; the pure helper's team branch is tested separately.
    header(detail({ created_by: "other", permission: "me" })); expect(screen.queryByTestId("chat-settings")).toBeNull(); expect(screen.queryByTestId("chat-more")).toBeNull();
  });
  it("keeps chat deletion available when the caller cannot manage the assistant", async () => {
    header(detail({ created_by: "other", permission: "me" }), true); fireEvent.pointerDown(screen.getByTestId("chat-more"), { button: 0, ctrlKey: false });
    await waitUntil(() => screen.queryByTestId("chat-menu-delete-chat")); expect(screen.queryByTestId("chat-menu-delete-assistant")).toBeNull();
  });
  it("shows the skipped-datasets notice with its plural count", () => {
    const assistant = detail(); assistant.kbIds = ["a"]; assistant.unavailableDatasets = 2; header(assistant);
    expect(screen.getByTestId("chat-datasets-notice")).toHaveTextContent("2 datasets used by this assistant aren't available to you and are skipped.");
  });
  it("shows the all-unavailable notice when no bound dataset is usable", () => {
    const assistant = detail(); assistant.unavailableDatasets = 1; header(assistant);
    expect(screen.getByTestId("chat-datasets-notice")).toHaveTextContent("None of this assistant's datasets are available to you");
  });
  it("shows no notice for a plain-chat assistant", () => { header(); expect(screen.queryByTestId("chat-datasets-notice")).toBeNull(); });
  it.each(["owner", "admin", "normal"])("shows shared-assistant management according to %s role", (role) => {
    if (role !== "owner") {
      const memberships = storedMemberships([membershipRow("t1", "Workspace", role)]);
      useUserStore.getState().setUser({ ...useUserStore.getState().user!, tenantId: "own" }); context.client.setQueryData(MEMBERSHIPS_QUERY_KEY, memberships);
      useWorkspaceStore.getState().initialise("u1", "own", memberships); useWorkspaceStore.getState().setActive("t1");
    }
    header(detail({ permission: "team", created_by: "other" }));
    expect(Boolean(screen.queryByTestId("chat-settings"))).toBe(role !== "normal"); expect(Boolean(screen.queryByTestId("chat-more"))).toBe(role !== "normal");
  });
});
