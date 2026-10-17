import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useDatasetBinding } from "./use-dataset-binding";

const USER: SessionUser = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};
const ID = "a".repeat(32);
const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

let datasetTenant = "t2";
const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  if (key === "GET /v1/tenant/list") return Promise.resolve(ok(config, []));
  if (key === `GET /api/v1/datasets/${ID}`) return Promise.resolve(ok(config, { id: ID, name: "Joined", tenant_id: datasetTenant }));
  return Promise.reject(new Error(`unexpected ${key}`));
};

function Probe() {
  const binding = useDatasetBinding({ datasetId: new URLSearchParams(window.location.search).get("id") ?? ID });
  return <p data-testid="probe">{`${binding.state}:${String(binding.bound)}`}</p>;
}

function mount(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  const router = createMemoryRouter(
    [
      { path: "/dataset/logs", element: <Probe /> },
      { path: "/datasets", element: <p data-testid="gallery">gallery</p> },
    ],
    { initialEntries: [entry] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  calls = [];
  datasetTenant = "t2";
  http.defaults.adapter = adapter;
  useUserStore.setState({ user: USER });
  useWorkspaceStore.getState().reset();
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("useDatasetBinding", () => {
  it("is not found without a request for a malformed id", async () => {
    window.history.replaceState({}, "", "/dataset/logs?id=nope");
    mount("/dataset/logs?id=nope");
    expect((await screen.findByTestId("probe")).textContent).toBe("not-found:false");
    expect(calls.some((c) => String(c.url).includes("/datasets/"))).toBe(false);
  });

  it("sends one detail request and is not bound before the store is initialised", async () => {
    window.history.replaceState({}, "", `/dataset/logs?id=${ID}`);
    mount(`/dataset/logs?id=${ID}`);
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("ready:false"));
    expect(calls.filter((c) => c.url === `/api/v1/datasets/${ID}`)).toHaveLength(1);
  });

  it("binds a deep link into a joined workspace without navigating away", async () => {
    useWorkspaceStore.getState().initialise("u1", "t1", [{ tenantId: "t2", name: "Joined", role: "normal" } as never]);
    window.history.replaceState({}, "", `/dataset/logs?id=${ID}`);
    const router = mount(`/dataset/logs?id=${ID}`);
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("ready:true"));
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t2");
    expect(router.state.location.pathname).toBe("/dataset/logs");
    expect(calls.filter((c) => c.url === `/api/v1/datasets/${ID}`)).toHaveLength(1);
  });

  it("navigates to /datasets when the user switches workspace", async () => {
    useWorkspaceStore.getState().initialise("u1", "t1", [{ tenantId: "t2", name: "Joined", role: "normal" } as never]);
    window.history.replaceState({}, "", `/dataset/logs?id=${ID}`);
    const router = mount(`/dataset/logs?id=${ID}`);
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("ready:true"));
    useWorkspaceStore.getState().setActive("t1");
    await waitFor(() => expect(router.state.location.pathname).toBe("/datasets"));
  });
});
