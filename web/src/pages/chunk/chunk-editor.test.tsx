import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { ApiError, registerQueryClient } from "@/services/http";
import type { ChunkView } from "@/services/chunk-service";
import { useUserStore } from "@/stores/user-store";
import { DATASET_ID } from "@/test/dataset-server";
import { server, useFilesServer } from "@/test/files-harness";
import { embeddedTexts, refuse, setTokenLimit, type Refusal } from "@/test/server-areas/chunk-edit";
import { chunkId, chunkRow, chunksOf, setChunks } from "@/test/server-areas/chunks";
import { waitUntil } from "@/test/wait-until";
import { ChunkEditor } from "./chunk-editor";
import { DiscardChangesDialog } from "./discard-dialog";
import { useEditGuard } from "./use-edit-guard";

useFilesServer();

const DOC = "d".repeat(31) + "1";
const CHUNKS_URL = `/api/v1/datasets/${DATASET_ID}/documents/${DOC}/chunks`;
const CHUNK_URL = `${CHUNKS_URL}/${chunkId(1)}`;
const SAVED = "Chunk text number 1";
const outcomes: { saved: ChunkView[]; closed: number } = { saved: [], closed: 0 };

function Host({ mode }: { mode: "edit" | "add" }) {
  const [dirty, setDirty] = useState(false);
  const [open, setOpen] = useState(true);
  const edit = useEditGuard(dirty);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  return (
    <>
      {open ? (
        <ChunkEditor
          mode={mode}
          datasetId={DATASET_ID}
          docId={DOC}
          chunk={mode === "edit" ? chunksOf(server, DOC)[0] : undefined}
          number={1}
          textareaRef={textarea}
          guard={edit.guard}
          onDirtyChange={setDirty}
          onClose={() => {
            edit.release();
            outcomes.closed += 1;
            setOpen(false);
          }}
          onSaved={(chunk) => {
            edit.release();
            outcomes.saved.push(chunk);
            setOpen(false);
          }}
        />
      ) : (
        <p data-testid="closed">closed</p>
      )}
      <DiscardChangesDialog
        open={edit.pending}
        onKeep={edit.cancel}
        onDiscard={edit.confirm}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          textarea.current?.focus();
        }}
      />
    </>
  );
}

let router: ReturnType<typeof createMemoryRouter>;

function renderEditor(mode: "edit" | "add" = "edit") {
  outcomes.saved = [];
  outcomes.closed = 0;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  router = createMemoryRouter(
    [
      { path: "/chunk", element: <Host mode={mode} /> },
      { path: "/datasets", element: <p data-testid="gallery">gallery</p> },
    ],
    { initialEntries: ["/chunk"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
}

const field = () => screen.getByLabelText("Chunk text") as HTMLTextAreaElement;
const saveButton = () => screen.getByRole("button", { name: /^(Save chunk|Add chunk)$/ });
const patches = () => server.callsTo("PATCH", CHUNK_URL);
const posts = () => server.callsTo("POST", CHUNKS_URL);

async function typeOver(text: string): Promise<void> {
  const user = userEvent.setup();
  await user.clear(field());
  await user.click(field());
  if (text !== "") await user.paste(text);
}

async function submitText(text: string): Promise<void> {
  await typeOver(text);
  await userEvent.setup().click(saveButton());
}

function seed(): void {
  setChunks(server, DOC, [chunkRow(1), chunkRow(2)]);
  server.documents[DATASET_ID] = (server.documents[DATASET_ID] ?? []).map((d, i) => (i === 0 ? { ...d, id: DOC, run: "3", chunk_num: 2 } : d));
}

describe("Layout (UI-17)", () => {
  it("edit: a labelled textarea holds the saved text with the cursor at its end, the helper and both buttons", () => {
    seed();
    renderEditor("edit");
    expect(field().value).toBe(SAVED);
    expect(field().selectionStart).toBe(SAVED.length);
    expect(document.activeElement).toBe(field());
    expect(screen.getByText("Edits are kept until this document is parsed again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard changes" })).toBeInTheDocument();
    expect(saveButton()).toHaveTextContent("Save chunk");
  });

  it("add: the New chunk heading, an empty textarea, the hand-added helper and an Add chunk button", () => {
    seed();
    renderEditor("add");
    expect(screen.getByRole("heading", { name: "New chunk" })).toBeInTheDocument();
    expect(field().value).toBe("");
    expect(screen.getByText("A chunk added by hand is searchable like any other. It has no place on a page and is lost if this document is parsed again.")).toBeInTheDocument();
    expect(saveButton()).toHaveTextContent("Add chunk");
  });
});

describe("Rules", () => {
  it("keeps the primary aria-disabled until the text differs, and a press does nothing", async () => {
    seed();
    renderEditor("edit");
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
    await userEvent.setup().click(saveButton());
    expect(patches()).toHaveLength(0);
    await userEvent.setup().type(field(), "!");
    expect(saveButton()).not.toHaveAttribute("aria-disabled", "true");
  });

  it("requires text after trimming and shows the message once the field was touched", async () => {
    seed();
    renderEditor("add");
    const user = userEvent.setup();
    expect(screen.queryByText("Enter the chunk's text.")).not.toBeInTheDocument();
    await user.click(field());
    await user.paste("   ");
    await user.tab();
    expect(await screen.findByText("Enter the chunk's text.")).toBeInTheDocument();
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
    expect(field()).toHaveAttribute("aria-invalid", "true");
    await user.click(saveButton());
    expect(posts()).toHaveLength(0);
  });

  it("refuses more than 32,000 characters before any request", async () => {
    seed();
    renderEditor("add");
    const user = userEvent.setup();
    await user.click(field());
    await user.paste("x".repeat(32001));
    expect(await screen.findByText("Use 32,000 characters or fewer.")).toBeInTheDocument();
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
    await user.click(saveButton());
    expect(posts()).toHaveLength(0);
    await user.keyboard("{Backspace}");
    expect(screen.queryByText("Use 32,000 characters or fewer.")).not.toBeInTheDocument();
    expect(saveButton()).not.toHaveAttribute("aria-disabled", "true");
  });

  it("saves on Ctrl+Enter", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Corrected text");
    fireEvent.keyDown(field(), { key: "Enter", ctrlKey: true });
    await waitUntil(() => patches().length === 1, { describe: "the PATCH" });
    expect(JSON.parse(String(patches()[0]?.data))).toEqual({ content_with_weight: "Corrected text" });
  });

  it("saves on Cmd+Enter and ignores a bare Enter", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Corrected text");
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(patches()).toHaveLength(0);
    fireEvent.keyDown(field(), { key: "Enter", metaKey: true });
    await waitUntil(() => patches().length === 1, { describe: "the PATCH" });
  });

  it("Esc on a clean editor closes it without asking", async () => {
    seed();
    renderEditor("edit");
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(await screen.findByTestId("closed")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("Esc on a changed editor asks, and Keep editing returns focus to the textarea with the text kept", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Half written");
    fireEvent.keyDown(field(), { key: "Escape" });
    const dialog = await screen.findByRole("alertdialog", { name: "Discard unsaved changes?" });
    expect(within(dialog).getByText("The text you typed for this chunk hasn't been saved.")).toBeInTheDocument();
    await userEvent.setup().click(within(dialog).getByRole("button", { name: "Keep editing" }));
    await waitUntil(() => screen.queryByRole("alertdialog") === null, { describe: "the dialog to close" });
    expect(field().value).toBe("Half written");
    await waitUntil(() => document.activeElement === field(), { describe: "focus on the textarea" });
  });

  it("Discard changes in the dialog runs the held action and closes the editor", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Half written");
    fireEvent.keyDown(field(), { key: "Escape" });
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.setup().click(within(dialog).getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByTestId("closed")).toBeInTheDocument();
    expect(patches()).toHaveLength(0);
  });

  it("the Discard button of the editor closes it and sends nothing", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Half written");
    await userEvent.setup().click(screen.getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByTestId("closed")).toBeInTheDocument();
    expect(patches()).toHaveLength(0);
    expect(chunksOf(server, DOC)[0]?.text).toBe(SAVED);
  });
});

describe("The Discard dialog", () => {
  it("focuses Keep editing first and does not close on a press outside", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Half written");
    fireEvent.keyDown(field(), { key: "Escape" });
    const dialog = await screen.findByRole("alertdialog");
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Keep editing" }));
    const overlay = document.querySelector<HTMLElement>('[data-state="open"].fixed.inset-0');
    if (overlay !== null) await userEvent.setup().click(overlay);
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("holds a route change the same way and lets it through on Discard changes", async () => {
    seed();
    renderEditor("edit");
    await typeOver("Half written");
    await act(async () => {
      await router.navigate("/datasets");
    });
    expect(router.state.location.pathname).toBe("/chunk");
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.setup().click(within(dialog).getByRole("button", { name: "Discard changes" }));
    await waitUntil(() => router.state.location.pathname === "/datasets", { describe: "the route change" });
  });
});

describe("Pending and success", () => {
  it("is busy and read-only while the write runs, announces it, and ignores a second submit", async () => {
    seed();
    let release: () => void = () => {};
    server.holds[`PATCH ${CHUNK_URL}`] = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderEditor("edit");
    await typeOver("Corrected text");
    const user = userEvent.setup();
    await user.click(saveButton());
    expect(await screen.findByText("Saving and updating the search index. This can take a few seconds.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saving and updating the search index.");
    expect(saveButton()).toHaveAttribute("aria-busy", "true");
    expect(field().readOnly).toBe(true);
    await user.click(saveButton());
    fireEvent.keyDown(field(), { key: "Enter", ctrlKey: true });
    release();
    await waitUntil(() => outcomes.saved.length === 1, { describe: "the save to finish" });
    expect(patches()).toHaveLength(1);
  });

  it("edit: stores the text, shows the toast and reports the saved chunk", async () => {
    seed();
    renderEditor("edit");
    await submitText("Corrected text");
    expect(await screen.findByText("Chunk saved")).toBeInTheDocument();
    await waitUntil(() => outcomes.saved.length === 1, { describe: "onSaved" });
    expect(outcomes.saved[0]).toMatchObject({ id: chunkId(1), text: "Corrected text", origin: "edited" });
    expect(chunksOf(server, DOC)[0]?.text).toBe("Corrected text");
    expect(patches()).toHaveLength(1);
  });

  it("add: posts the text, shows the toast and reports the new chunk", async () => {
    seed();
    renderEditor("add");
    await submitText("Written by hand");
    expect(await screen.findByText("Chunk added")).toBeInTheDocument();
    await waitUntil(() => outcomes.saved.length === 1, { describe: "onSaved" });
    expect(outcomes.saved[0]).toMatchObject({ text: "Written by hand", origin: "manual", positions: [] });
    expect(JSON.parse(String(posts()[0]?.data))).toEqual({ content_with_weight: "Written by hand" });
    expect(posts()).toHaveLength(1);
    expect(chunksOf(server, DOC)).toHaveLength(3);
  });
});

interface Case {
  name: string;
  refusal: Refusal;
  reason: string;
  limit?: number;
}

const CASES: Case[] = [
  { name: "502 provider_timeout", refusal: { status: 502, reason: "provider_timeout" }, reason: "The embedding provider timed out." },
  { name: "504 gateway timeout", refusal: { status: 504 }, reason: "The embedding provider timed out." },
  { name: "a client timeout", refusal: { timeout: true }, reason: "The embedding provider timed out." },
  { name: "400 provider_refused", refusal: { status: 400, reason: "provider_refused" }, reason: "The embedding provider refused the text." },
  { name: "429", refusal: { status: 429, reason: "provider_rate_limited" }, reason: "The embedding provider is limiting requests. Wait a moment and try again." },
  { name: "503 provider_rate_limited", refusal: { status: 503, reason: "provider_rate_limited" }, reason: "The embedding provider is limiting requests. Wait a moment and try again." },
  { name: "409 model_unavailable", refusal: { status: 409, reason: "model_unavailable" }, reason: "This dataset's embedding model is no longer available in the workspace." },
  { name: "400 chunk_too_long", refusal: { status: 400, reason: "chunk_too_long" }, reason: "This text is longer than the embedding model accepts. Shorten it or split it into two chunks." },
  { name: "503 index_unavailable", refusal: { status: 503, reason: "index_unavailable" }, reason: "The search index isn't available right now." },
  { name: "409 parse_running", refusal: { status: 409, reason: "parse_running" }, reason: "This document is being parsed. Editing is paused until parsing ends." },
  { name: "404", refusal: { status: 404, reason: "not_found" }, reason: "This chunk no longer exists. The document was parsed again or deleted." },
  { name: "403", refusal: { status: 403, reason: "forbidden" }, reason: "You don't have permission to do that in Ada's workspace. Your role may have changed." },
  { name: "provider_unreachable", refusal: { status: 502, reason: "provider_unreachable" }, reason: "The embedding provider couldn't be reached." },
  { name: "dimension_mismatch", refusal: { status: 400, reason: "dimension_mismatch" }, reason: "The embedding model returned vectors of a different size than this dataset uses." },
  { name: "an unexpected answer", refusal: { status: 500 }, reason: "The connection was lost or the server didn't answer." },
];

describe("Refusals of an edit (D-11)", () => {
  it.each(CASES)("$name: names the reason, keeps the typed text and the stored text", async ({ refusal, reason }) => {
    seed();
    refuse(server, "update", refusal);
    renderEditor("edit");
    await submitText("Corrected text");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The chunk wasn't saved")).toBeInTheDocument();
    expect(within(alert).getByText(reason)).toBeInTheDocument();
    expect(within(alert)).toHaveTextContent("The text in the search index is unchanged.");
    await waitUntil(() => document.activeElement === alert, { describe: "focus on the alert" });
    expect(field().value).toBe("Corrected text");
    expect(field().readOnly).toBe(false);
    expect(patches()).toHaveLength(1);
    expect(chunksOf(server, DOC)[0]?.text).toBe(SAVED);
    expect(outcomes.saved).toHaveLength(0);
    expect(screen.queryByText("Chunk saved")).not.toBeInTheDocument();
  });

  it("refuses text the model cannot take with the too-long reason", async () => {
    seed();
    setTokenLimit(server, 10);
    renderEditor("edit");
    await submitText("This text is far too long for the model");
    expect(await screen.findByText(/longer than the embedding model accepts/)).toBeInTheDocument();
    expect(embeddedTexts(server)).toHaveLength(1);
  });

  it("shows the provider's own sentence as text, bounded to 300 characters", async () => {
    seed();
    const hostile = `<img src=x onerror=alert(1)>${"y".repeat(400)}`;
    refuse(server, "update", { status: 400, reason: "provider_refused", detail: hostile });
    renderEditor("edit");
    await submitText("Corrected text");
    const alert = await screen.findByRole("alert");
    const detail = within(alert).getByTestId("chunk-editor-detail");
    expect(detail.textContent).toBe(hostile.slice(0, 300));
    expect(alert.querySelector("img")).toBeNull();
  });

  it("falls back to the fixed line when the provider's sentence is empty", async () => {
    seed();
    refuse(server, "update", { status: 400, reason: "provider_refused", detail: "   " });
    renderEditor("edit");
    await submitText("Corrected text");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The embedding provider refused the text.")).toBeInTheDocument();
    expect(within(alert).queryByTestId("chunk-editor-detail")).not.toBeInTheDocument();
  });

  it("is never a session event: no 401 handling, the user stays signed in", async () => {
    seed();
    refuse(server, "update", { status: 400, reason: "provider_refused" });
    renderEditor("edit");
    await submitText("Corrected text");
    await screen.findByRole("alert");
    expect(useUserStore.getState().user).not.toBeNull();
    expect(screen.queryByText(/session expired/i)).not.toBeInTheDocument();
  });

  it("can be retried: the same text goes out again and the second answer saves it", async () => {
    seed();
    refuse(server, "update", { status: 503, reason: "index_unavailable", times: 1 });
    renderEditor("edit");
    await submitText("Corrected text");
    await screen.findByRole("alert");
    await userEvent.setup().click(saveButton());
    await waitUntil(() => outcomes.saved.length === 1, { describe: "the retry to save" });
    expect(patches()).toHaveLength(2);
    expect(embeddedTexts(server)).toEqual(["Corrected text", "Corrected text"]);
    expect(chunksOf(server, DOC)[0]?.text).toBe("Corrected text");
  });

  it("Discard changes after a refusal closes the editor and the saved text stays", async () => {
    seed();
    refuse(server, "update", { status: 503, reason: "index_unavailable" });
    renderEditor("edit");
    await submitText("Corrected text");
    await screen.findByRole("alert");
    await userEvent.setup().click(screen.getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByTestId("closed")).toBeInTheDocument();
    expect(chunksOf(server, DOC)[0]?.text).toBe(SAVED);
  });

  it("a stale refusal does not show for another chunk's editor", async () => {
    seed();
    refuse(server, "update", { status: 503, reason: "index_unavailable" });
    const view = renderEditor("edit");
    await submitText("Corrected text");
    await screen.findByRole("alert");
    view.unmount();
    renderEditor("edit");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(field().value).toBe(SAVED);
  });
});

describe("Refusals of an add (D-11)", () => {
  it("names the reason, leaves out the unchanged sentence and keeps the text", async () => {
    seed();
    refuse(server, "create", { status: 409, reason: "model_unavailable" });
    renderEditor("add");
    await submitText("Written by hand");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The chunk wasn't added")).toBeInTheDocument();
    expect(within(alert).getByText("This dataset's embedding model is no longer available in the workspace.")).toBeInTheDocument();
    expect(alert).not.toHaveTextContent("The text in the search index is unchanged.");
    await waitUntil(() => document.activeElement === alert, { describe: "focus on the alert" });
    expect(field().value).toBe("Written by hand");
    expect(posts()).toHaveLength(1);
    expect(chunksOf(server, DOC)).toHaveLength(2);
  });

  it("a 404 says the document is gone", async () => {
    seed();
    refuse(server, "create", { status: 404, reason: "not_found" });
    renderEditor("add");
    await submitText("Written by hand");
    expect(await screen.findByText("This document no longer exists.")).toBeInTheDocument();
  });

  it("a client timeout names the provider and stores nothing", async () => {
    seed();
    refuse(server, "create", { timeout: true });
    renderEditor("add");
    await submitText("Written by hand");
    expect(await screen.findByText("The embedding provider timed out.")).toBeInTheDocument();
    expect(chunksOf(server, DOC)).toHaveLength(2);
  });
});

describe("Failure placement is by status and kind, never by text (FE-06)", () => {
  it("recognises a timeout from the error's kind", async () => {
    const { isTimeout } = await import("../dataset/errors");
    expect(isTimeout(new ApiError({ code: -1, message: "anything", status: 0, kind: "timeout" }))).toBe(true);
    expect(isTimeout(new ApiError({ code: -1, message: "timeout", status: 0, kind: "network" }))).toBe(false);
  });
});
