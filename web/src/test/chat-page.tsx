import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import ChatPage from "@/pages/chat";
import { createDatasetServer } from "./dataset-server";
import { assistantRow, setAssistants } from "./server-areas/assistants";
import { sessionRow, setSessions } from "./server-areas/chat";

export const A = assistantRow().id, B = assistantRow(2).id, S = sessionRow().id;
export const chatUser = { id: "u1", nickname: "Ada", email: "ada@example.test", avatar: "", language: "English", colorSchema: "Bright", tenantId: "t1", tenantName: "Workspace", role: "owner", isSuperuser: false };
export function chatSetup() {
  vi.stubGlobal("matchMedia", (media: string) => ({ matches: true, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  const server = createDatasetServer(); server.reset(); http.defaults.adapter = server.adapter;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); registerQueryClient(client);
  useUserStore.getState().setUser(chatUser); setAuthorization("chat-test");
  useWorkspaceStore.getState().reset(); useWorkspaceStore.getState().initialise("u1", "t1", []);
  client.setQueryData(MEMBERSHIPS_QUERY_KEY, []);
  setAssistants(server, [assistantRow(), assistantRow(2)]); setSessions(server, [sessionRow()]);
  server.use(({ method, url, params, ok }) => {
    if (method === "GET" && url === "/api/v1/models") return ok(params.type === "rerank" ? [] : [{ id: "chat-one@OpenRouter", name: "chat-one", provider: "OpenRouter", type: "chat" }]);
    if (method === "GET" && url === "/api/v1/datasets") return ok({ items: [], total: 0 });
    return undefined;
  });
  const mount = (path = "/chats") => {
    const router = createMemoryRouter([{ path: "/chats", element: <ChatPage /> }], { initialEntries: [path] });
    return { ...render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>), router };
  };
  return { server, client, mount };
}
