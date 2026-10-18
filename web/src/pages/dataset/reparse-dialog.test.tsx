import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { PARSE_URL, renderTable, rowOf, sent, server, useFilesServer } from "@/test/files-harness";
import { setFileExtra } from "@/test/server-areas/files";

useFilesServer();

/** Two finished documents, the first with edits; opens the dialog for the first one from its menu. */
async function openFor(n: number) {
  await userEvent.click(within(rowOf(n)).getByTestId("document-more"));
  await userEvent.click(await screen.findByTestId("document-menu-reparse"));
  return screen.findByTestId("reparse-dialog");
}

function finished() {
  server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 6 }), documentRow(2, { run: "3", chunk_num: 3 })];
  setFileExtra(server, documentRow(1).id, { editedCount: 2, manualCount: 1 });
}

describe("ReparseDialog, one document", () => {
  it("names the document, shows all three counts, the loss sentence and the closing line, and focuses 'Keep chunks'", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    const dialog = await openFor(1);
    expect(within(dialog).getByRole("heading", { name: "Parse again and replace chunks?" })).toBeInTheDocument();
    expect(within(dialog).getByText('"report-01.pdf" will be rebuilt from its stored file. Every chunk it has now is replaced.')).toBeInTheDocument();
    expect(within(dialog).getByText("Chunks that will be replaced")).toBeInTheDocument();
    expect(within(dialog).getByText("Edited chunks that will be lost")).toBeInTheDocument();
    expect(within(dialog).getByText("Hand-added chunks that will be lost")).toBeInTheDocument();
    expect(within(dialog).getByTestId("reparse-loss-note")).toHaveTextContent("Edits and hand-added chunks can't be recovered.");
    expect(within(dialog).getByText("Until parsing finishes, this document returns fewer results in search.")).toBeInTheDocument();
    expect(within(dialog).queryByTestId("reparse-list")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("reparse-keep")).toHaveFocus());
    expect(dialog.className).toContain("max-w-md");
  });

  it("shows the no-loss sentence and zero rows when nothing was edited", async () => {
    finished();
    const dialog = await (async () => {
      renderTable();
      await screen.findByTestId("documents-table");
      return openFor(2);
    })();
    expect(within(dialog).getByTestId("reparse-loss-note")).toHaveTextContent("No chunk of this document was edited or added by hand.");
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("0");
    expect(within(dialog).getByTestId("reparse-manual")).toHaveTextContent("0");
  });

  it("keeps the chunks, sends nothing more and returns focus to the row's menu button", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await openFor(1);
    await userEvent.click(screen.getByTestId("reparse-keep"));
    await waitFor(() => expect(screen.queryByTestId("reparse-dialog")).toBeNull());
    expect(server.callsTo("POST", PARSE_URL)).toHaveLength(1);
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-more")).toHaveFocus());
    expect(rowOf(1)).toHaveAttribute("data-run", "3");
  });

  it("resends with confirm_replace, stays open and busy until the server answers, ignores Escape, then closes with focus on the menu button and no toast", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await openFor(1);
    let release: () => void = () => {};
    server.holds[`POST ${PARSE_URL}`] = new Promise<void>((resolve) => (release = resolve));
    const confirm = screen.getByTestId("reparse-confirm");
    await userEvent.click(confirm);
    await waitFor(() => expect(confirm).toHaveAttribute("aria-busy", "true"));
    expect(confirm).toHaveAttribute("aria-disabled", "true");
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByTestId("reparse-keep"));
    expect(screen.getByTestId("reparse-dialog")).toBeInTheDocument();
    await userEvent.click(confirm);
    release();
    await waitFor(() => expect(screen.queryByTestId("reparse-dialog")).toBeNull());
    expect(sent(PARSE_URL)).toEqual([
      { doc_ids: [documentRow(1).id], run: "1" },
      { doc_ids: [documentRow(1).id], run: "1", confirm_replace: true },
    ]);
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-more")).toHaveFocus());
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("shows the fixed copy inline when the replace fails and keeps the dialog open", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await openFor(1);
    server.forced[`POST ${PARSE_URL}`] = { status: 503, message: "x", reason: "index_unavailable" };
    await userEvent.click(screen.getByTestId("reparse-confirm"));
    expect(await screen.findByTestId("reparse-error")).toHaveTextContent("The search index isn't available right now. Nothing was changed. Try again in a moment.");
    expect(screen.getByTestId("reparse-dialog")).toBeInTheDocument();
  });

  it("uses the lost-permission copy for a 403", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await openFor(1);
    server.forced[`POST ${PARSE_URL}`] = { status: 403, message: "x" };
    await userEvent.click(screen.getByTestId("reparse-confirm"));
    expect(await screen.findByTestId("reparse-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace. Your role may have changed.");
  });

  it("refreshes the numbers in place on a second confirm_required and says the counts changed", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    const dialog = await openFor(1);
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("2");
    act(() => setFileExtra(server, documentRow(1).id, { editedCount: 5, refuseConfirmOnce: true }));
    await userEvent.click(screen.getByTestId("reparse-confirm"));
    expect(await screen.findByTestId("reparse-changed")).toHaveTextContent("The counts changed. Check them and confirm again.");
    expect(within(screen.getByTestId("reparse-dialog")).getByTestId("reparse-edited")).toHaveTextContent("5");
    await userEvent.click(screen.getByTestId("reparse-confirm"));
    await waitFor(() => expect(screen.queryByTestId("reparse-dialog")).toBeNull());
  });

  it("never shows an error from document A when the dialog opens for document B (FE-04)", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await openFor(1);
    server.forced[`POST ${PARSE_URL}`] = { status: 503, message: "x", reason: "index_unavailable" };
    await userEvent.click(screen.getByTestId("reparse-confirm"));
    await screen.findByTestId("reparse-error");
    delete server.forced[`POST ${PARSE_URL}`];
    await userEvent.click(screen.getByTestId("reparse-keep"));
    await waitFor(() => expect(screen.queryByTestId("reparse-dialog")).toBeNull());
    const second = await openFor(2);
    expect(within(second).queryByTestId("reparse-error")).toBeNull();
    expect(within(second).queryByTestId("reparse-changed")).toBeNull();
    expect(within(second).getByText('"report-02.pdf" will be rebuilt from its stored file. Every chunk it has now is replaced.')).toBeInTheDocument();
  });
});

describe("ReparseDialog, several documents", () => {
  it("shows the title, the totals, a scrolling list with per-row counts and the hand-edit line", async () => {
    finished();
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("documents-select-all"));
    await userEvent.click(screen.getByTestId("selection-parse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(within(dialog).getByRole("heading", { name: "Parse 2 documents again?" })).toBeInTheDocument();
    expect(within(dialog).getByText("2 of the selected documents already have chunks. Each one is rebuilt from its stored file and its chunks are replaced.")).toBeInTheDocument();
    expect(within(dialog).getByTestId("reparse-chunks")).toHaveTextContent("9");
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("2");
    expect(within(dialog).getByTestId("reparse-manual")).toHaveTextContent("1");
    const list = within(dialog).getByTestId("reparse-list");
    expect(list.className).toContain("max-h-40");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("report-01.pdf");
    expect(items[0]).toHaveTextContent("6 chunks");
    expect(items[0]).toHaveTextContent("2 edited, 1 added by hand");
    expect(items[1]).toHaveTextContent("3 chunks");
    expect(items[1]).not.toHaveTextContent("edited");
    expect(within(dialog).getByText("Until parsing finishes, these documents return fewer results in search.")).toBeInTheDocument();
  });

  it("renders hostile names in the list as text", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 2, name: "<b>bold</b>.pdf" }), documentRow(2, { run: "3", chunk_num: 1 })];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("documents-select-all"));
    await userEvent.click(screen.getByTestId("selection-parse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(within(dialog).getByText("<b>bold</b>.pdf")).toBeInTheDocument();
    expect(dialog.querySelector("b")).toBeNull();
  });
});
