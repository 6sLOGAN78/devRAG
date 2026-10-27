import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/services/http";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUserStore } from "@/stores/user-store";
import { A, B, S, chatSetup } from "@/test/chat-page";
import { assistantRow, setAssistants } from "@/test/server-areas/assistants";
import { sessionRow, setSessions } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";

describe("assistant and chat rail", () => {
  const adapter = http.defaults.adapter; let context: ReturnType<typeof chatSetup>;
  beforeEach(() => { context = chatSetup(); });
  afterEach(() => { cleanup(); context.client.clear(); http.defaults.adapter = adapter; useWorkspaceStore.getState().reset(); useUserStore.getState().reset(); vi.unstubAllGlobals(); });
  const ready = () => waitUntil(() => screen.queryAllByTestId("rail-assistant-row").length > 0);
  it("auto-selects the first assistant with replace", async () => {
    const { router } = context.mount(); await ready(); await waitUntil(() => router.state.location.search.includes(A));
    expect(router.state.historyAction).toBe("REPLACE"); expect(screen.getAllByTestId("rail-assistant-row")[0]).toHaveAttribute("aria-current", "true");
  });
  it("keeps both valid parameters on a reload", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`); await ready();
    await waitUntil(() => screen.queryByTestId("rail-chat-row")); expect(router.state.location.search).toBe(`?chat=${A}&session=${S}`);
    expect(screen.getByTestId("rail-chat-row")).toHaveAttribute("aria-current", "true");
  });
  it("ignores malformed chat and session ids before building requests", async () => {
    context.mount("/chats?chat=../../../secret&session=ABC"); await ready();
    expect(context.server.calls.some((call) => String(call.url).includes("secret") || String(call.url).includes("ABC"))).toBe(false);
  });
  it("does not request a malformed session under a valid assistant", async () => {
    context.mount(`/chats?chat=${A}&session=bad`); await ready();
    expect(context.server.callsTo("GET", `/api/v1/chats/${A}/sessions/bad`)).toHaveLength(0);
  });
  it("sends nothing until the workspace store is initialized", async () => {
    useWorkspaceStore.getState().reset(); context.mount(`/chats?chat=${A}&session=${S}`);
    expect(context.server.callsTo("GET", "/api/v1/chats")).toHaveLength(0); expect(context.server.callsTo("GET", `/api/v1/chats/${A}`)).toHaveLength(0);
    act(() => useWorkspaceStore.getState().initialise("u1", "t1", [])); await ready();
  });
  it("switching assistant clears the selected chat", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`); await ready();
    fireEvent.click(screen.getAllByTestId("rail-assistant-row")[1]!); await waitUntil(() => router.state.location.search === `?chat=${B}`);
  });
  it("New chat clears only the session", async () => {
    const { router } = context.mount(`/chats?chat=${A}&session=${S}`); await ready(); fireEvent.click(screen.getByTestId("rail-chat-new"));
    expect(router.state.location.search).toBe(`?chat=${A}`);
  });
  it("selects a stored chat in the URL", async () => {
    const { router } = context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByTestId("rail-chat-row"));
    fireEvent.click(screen.getByTestId("rail-chat-row")); expect(router.state.location.search).toBe(`?chat=${A}&session=${S}`);
  });
  it("never lists another person's private assistant", async () => {
    setAssistants(context.server, [assistantRow(), assistantRow(2, { created_by: "other" })]); context.mount(); await ready();
    expect(screen.getAllByTestId("rail-assistant-row")).toHaveLength(1); expect(screen.queryByText("Assistant 2")).toBeNull();
  });
  it("renders initials without requesting icons for the list", async () => {
    context.mount(); await ready(); const row = screen.getAllByTestId("rail-assistant-row")[0]!;
    expect(within(row).getByTestId("avatar-initials")).toHaveTextContent("A1"); expect(row.querySelector("img")).toBeNull();
  });
  it("searches after the debounce without changing the URL or input focus", async () => {
    const { router } = context.mount(`/chats?chat=${A}`); await ready(); const input = screen.getByRole("searchbox", { name: "Search assistants" }); input.focus();
    const before = context.server.callsTo("GET", "/api/v1/chats").length; fireEvent.change(input, { target: { value: "Assistant 2" } });
    expect(context.server.callsTo("GET", "/api/v1/chats")).toHaveLength(before);
    await waitUntil(() => context.server.callsTo("GET", "/api/v1/chats").some((call) => call.params?.keywords === "Assistant 2"));
    expect(input).toHaveFocus(); expect(router.state.location.search).toBe(`?chat=${A}`);
  });
  it("shows a no-match state while retaining the search field", async () => {
    context.mount(); await ready(); fireEvent.change(screen.getByRole("searchbox"), { target: { value: "unmatched" } });
    await waitUntil(() => screen.queryByText("No assistants match.")); expect(screen.getByRole("searchbox")).toHaveValue("unmatched");
  });
  it("retains keyboard focus on Next while fetching the last assistant page", async () => {
    setAssistants(context.server, Array.from({ length: 21 }, (_, i) => assistantRow(i + 1))); context.mount(); await ready();
    const next = within(screen.getByRole("navigation", { name: "Assistant pages" })).getByRole("button", { name: "Next" }); next.focus();
    let release = () => {}; context.server.holds["GET /api/v1/chats"] = new Promise<void>((resolve) => { release = resolve; });
    await userEvent.keyboard("{Enter}"); await waitUntil(() => context.server.callsTo("GET", "/api/v1/chats").some((call) => call.params?.page === 2)); expect(next).toHaveFocus();
    await act(async () => release()); await waitUntil(() => screen.queryAllByTestId("rail-assistant-row").length === 1); expect(next).toHaveFocus(); expect(next).toHaveAttribute("aria-disabled", "true");
  });
  it("shows no chats and hides one-page controls", async () => {
    setSessions(context.server, []); context.mount(); await ready(); await waitUntil(() => screen.queryByText("No chats yet. Send a message to start one."));
    expect(screen.queryByTestId("rail-assistant-pages")).toBeNull(); expect(screen.queryByTestId("rail-chat-pages")).toBeNull();
  });
  it("shows only the caller's own chats and uses New chat for an unnamed one", async () => {
    setSessions(context.server, [sessionRow(1, { name: "" }), sessionRow(2, { created_by: "other" })]); context.mount();
    await waitUntil(() => screen.queryByTestId("rail-chat-row")); expect(screen.getAllByTestId("rail-chat-row")).toHaveLength(1); expect(screen.getByTestId("rail-chat-row")).toHaveTextContent("New chat");
  });
  it("retries the assistant list without losing the rail header", async () => {
    context.server.forced["GET /api/v1/chats"] = { status: 502, message: "failure" }; context.mount();
    await waitUntil(() => screen.queryByText("Couldn't load assistants.")); expect(screen.getByTestId("rail-assistant-new")).toBeInTheDocument();
    delete context.server.forced["GET /api/v1/chats"]; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await ready();
  });
  it("keeps assistants usable when the chat list fails", async () => {
    context.server.forced[`GET /api/v1/chats/${A}/sessions`] = { status: 502, message: "failure" }; context.mount(`/chats?chat=${A}`);
    await waitUntil(() => screen.queryByText("Couldn't load chats.")); expect(screen.getAllByTestId("rail-assistant-row")).toHaveLength(2);
  });
  it("pages the caller's chats while retaining focus", async () => {
    setSessions(context.server, Array.from({ length: 21 }, (_, index) => sessionRow(index + 1)));
    context.mount(`/chats?chat=${A}`); await waitUntil(() => screen.queryByRole("navigation", { name: "Chat pages" }));
    const next = within(screen.getByRole("navigation", { name: "Chat pages" })).getByRole("button", { name: "Next" }); next.focus();
    await userEvent.keyboard("{Enter}"); await waitUntil(() => screen.queryAllByTestId("rail-chat-row").length === 1);
    expect(next).toHaveFocus(); expect(context.server.callsTo("GET", `/api/v1/chats/${A}/sessions`).at(-1)?.params).toMatchObject({ page: 2, page_size: 20 });
  });
});
