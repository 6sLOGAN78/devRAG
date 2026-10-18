import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, vi } from "vitest";
import { DatasetFiles } from "@/pages/dataset/dataset-files";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { DATASET_ID, createDatasetServer, datasetRow, documentRow, membershipRow, storedMemberships } from "./dataset-server";

/** The document table against the in-memory server, shared by the parse-control and dialog suites. */
export const OWNER: SessionUser = {
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

export const server = createDatasetServer();
export const DATASET = { id: DATASET_ID, name: "Reports", createdBy: "u1", tenantId: "t1" };
export const DOCS_URL = `/api/v1/datasets/${DATASET_ID}/documents`;
export const PARSE_URL = `${DOCS_URL}/parse`;
export const STATUS_URL = `${DOCS_URL}/batch-update-status`;
const originalAdapter = http.defaults.adapter;

function Harness({ initialPage = 1 }: { initialPage?: number }) {
  const [page, setPage] = useState(initialPage);
  const [keywords, setKeywords] = useState("");
  return (
    <>
      <DatasetFiles
        dataset={DATASET}
        limits={null}
        page={page}
        keywords={keywords}
        onPageChange={setPage}
        onSearch={(next) => {
          setKeywords(next);
          setPage(1);
        }}
        onUpload={() => {}}
      />
      <p data-testid="state">{`${page}|${keywords}`}</p>
    </>
  );
}

export function renderTable(props: { initialPage?: number } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  const view = render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Harness {...props} />
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { ...view, client };
}

export function actAs(user: SessionUser, role: string, uploader = "u1"): void {
  server.memberships = [membershipRow(user.tenantId, user.tenantName, "owner", user.nickname), membershipRow("t1", "Ada's workspace", role, "Ada")];
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(user);
  useWorkspaceStore.getState().initialise(user.id, user.tenantId, storedMemberships(server.memberships));
  useWorkspaceStore.getState().setActive("t1");
  server.documents[DATASET_ID] = (server.documents[DATASET_ID] ?? []).map((d) => ({ ...d, created_by: uploader }));
}

export function useFilesServer(): void {
  beforeEach(() => {
    server.reset();
    server.memberships = [membershipRow("t1", "Ada's workspace", "owner", "Ada")];
    server.datasets[DATASET_ID] = datasetRow();
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2), documentRow(3)];
    useUserStore.getState().reset();
    useWorkspaceStore.getState().reset();
    useUserStore.getState().setUser(OWNER);
    useWorkspaceStore.getState().initialise("u1", "t1", storedMemberships(server.memberships));
    setAuthorization("tok-session");
    http.defaults.adapter = server.adapter;
  });
  afterEach(() => {
    vi.useRealTimers();
    http.defaults.adapter = originalAdapter;
    useUserStore.getState().reset();
    useWorkspaceStore.getState().reset();
  });
}

export const rows = () => document.querySelectorAll<HTMLElement>('[data-testid="document-row"]');
export const rowOf = (n: number): HTMLElement => document.querySelector<HTMLElement>(`[data-doc-id="${documentRow(n).id}"]`) as HTMLElement;
export const sent = (url: string, method = "POST") => server.callsTo(method, url).map((c) => JSON.parse(String(c.data)) as Record<string, unknown>);
