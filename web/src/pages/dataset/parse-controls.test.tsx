import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { DOCS_URL, OWNER, PARSE_URL, STATUS_URL, actAs, renderTable, rowOf, sent, server, useFilesServer } from "@/test/files-harness";
import { advanceParse, setFileExtra } from "@/test/server-areas/files";

useFilesServer();

const listCalls = () => server.callsTo("GET", DOCS_URL);
const MEMBER: SessionUser = { ...OWNER, id: "u4", nickname: "Dan", tenantId: "t4", tenantName: "Dan's workspace" };

describe("Which control a row offers (D-01, D-02, D-10)", () => {
  it("offers Parse on an unparsed parseable row and nothing on one that cannot be parsed", async () => {
    setFileExtra(server, documentRow(2).id, { parseable: false });
    renderTable();
    await screen.findByTestId("documents-table");
    expect(within(rowOf(1)).getByRole("button", { name: "Parse report-01.pdf" })).toHaveTextContent("Parse");
    expect(within(rowOf(2)).queryByTestId("document-parse")).toBeNull();
    expect(within(rowOf(2)).queryByTestId("document-select")).toBeNull();
  });

  it("offers Cancel parsing on a running row, Parse again on failed, cancelled and partly indexed rows, and nothing on a finished one", async () => {
    server.documents[DATASET_ID] = [
      documentRow(1, { run: "1", progress: 0.2 }),
      documentRow(2, { run: "4" }),
      documentRow(3, { run: "2" }),
      documentRow(4, { run: "4", chunk_num: 3 }),
      documentRow(5, { run: "3", chunk_num: 3 }),
    ];
    renderTable();
    await screen.findByTestId("documents-table");
    expect(within(rowOf(1)).getByRole("button", { name: "Cancel parsing report-01.pdf" })).toBeInTheDocument();
    for (const n of [2, 3, 4]) expect(within(rowOf(n)).getByRole("button", { name: `Parse report-0${n}.pdf again` })).toBeInTheDocument();
    expect(within(rowOf(5)).queryByTestId("document-parse")).toBeNull();
    expect(within(rowOf(5)).queryByTestId("document-cancel")).toBeNull();
    expect(within(rowOf(5)).queryByTestId("document-reparse")).toBeNull();
  });

  it("gives a member who may not change the document status, read-only text and the read-only menu items, and no control", async () => {
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2, { run: "1", progress: 0.2 }), documentRow(3, { run: "4" })];
    actAs(MEMBER, "normal", "u1");
    renderTable();
    await screen.findByTestId("documents-table");
    for (const id of ["document-parse", "document-cancel", "document-reparse", "document-select", "documents-select-all", "document-search-switch", "document-delete"]) {
      expect(screen.queryByTestId(id), id).toBeNull();
    }
    expect(screen.getAllByTestId("document-search-text")).toHaveLength(3);
    await userEvent.click(within(rowOf(1)).getByTestId("document-more"));
    expect(await screen.findByTestId("document-menu-chunks")).toBeInTheDocument();
    expect(screen.getByTestId("document-menu-open")).toBeInTheDocument();
    expect(screen.queryByTestId("document-menu-reparse")).toBeNull();
  });

  it("gives a member the controls on their own uploads", async () => {
    actAs(MEMBER, "normal", "u4");
    renderTable();
    await screen.findByTestId("documents-table");
    expect(within(rowOf(1)).getByTestId("document-parse")).toBeInTheDocument();
    expect(within(rowOf(1)).getByTestId("document-search-switch")).toBeInTheDocument();
  });
});

describe("Pressing Parse (UI-15, FE-01)", () => {
  it("sends one request, shows no toast and moves the row to Parsing with a bar and 'Waiting for a worker'", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-parse"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    expect(sent(PARSE_URL)).toEqual([{ doc_ids: [documentRow(1).id], run: "1" }]);
    expect(within(rowOf(1)).getByTestId("document-status")).toHaveTextContent("Parsing");
    expect(within(rowOf(1)).getByRole("progressbar", { name: "Parsing progress for report-01.pdf" })).toBeInTheDocument();
    expect(within(rowOf(1)).getByTestId("document-progress-message")).toHaveTextContent("Waiting for a worker");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("marks the button aria-disabled and aria-busy while the request is in flight and sends no second request", async () => {
    let release: () => void = () => {};
    server.holds[`POST ${PARSE_URL}`] = new Promise<void>((resolve) => (release = resolve));
    renderTable();
    await screen.findByTestId("documents-table");
    const button = within(rowOf(1)).getByTestId("document-parse");
    await userEvent.click(button);
    await waitFor(() => expect(button).toHaveAttribute("aria-busy", "true"));
    expect(button).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(button);
    release();
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    expect(sent(PARSE_URL)).toHaveLength(1);
  });

  it("updates the running row in place on its own and keeps focus and an open menu", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-parse"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    const menuButton = within(rowOf(2)).getByTestId("document-more");
    await userEvent.click(menuButton);
    await screen.findByTestId("document-menu");
    const before = listCalls().length;
    act(() => advanceParse(server, documentRow(1).id, { run: "1", progress: 0.4, message: "Embedding 2 of 5" }));
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-progress-message")).toHaveTextContent("Embedding 2 of 5"), { timeout: 5000 });
    expect(listCalls().length).toBeGreaterThan(before);
    expect(within(rowOf(1)).getByTestId("document-progress")).toHaveTextContent("40%");
    expect(screen.getByTestId("document-menu")).toBeInTheDocument();
    act(() => advanceParse(server, documentRow(1).id, { run: "3", progress: 1, chunkCount: 5 }));
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-status")).toHaveTextContent("Finished"), { timeout: 5000 });
    expect(within(rowOf(1)).getByTestId("document-status-detail")).toHaveTextContent("5 chunks");
  }, 15000);

  it("starts a cancel with one request, no confirmation, and shows Cancelled", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.3 })];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-cancel"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "2"));
    expect(sent(PARSE_URL)).toEqual([{ doc_ids: [documentRow(1).id], run: "2" }]);
    expect(within(rowOf(1)).getByTestId("document-status")).toHaveTextContent("Cancelled");
    expect(screen.queryByTestId("reparse-dialog")).toBeNull();
  });
});

describe("Refused parse requests", () => {
  const cases: Array<[string, { status: number; reason?: string }, string]> = [
    ["parse_unavailable", { status: 400, reason: "parse_unavailable" }, "Parsing isn't available yet for this file type."],
    ["chunker_unavailable", { status: 400, reason: "chunker_unavailable" }, "This document is set to a chunking method that isn't available yet. Choose General, then parse."],
    ["model_unavailable", { status: 409, reason: "model_unavailable" }, "This dataset's embedding model is no longer available in the workspace. Add it again in model settings, then parse."],
    ["queue_unavailable", { status: 503, reason: "queue_unavailable" }, "The parsing queue isn't available right now. Nothing was started. Try again in a moment."],
    ["index_unavailable", { status: 503, reason: "index_unavailable" }, "The search index isn't available right now. Nothing was changed. Try again in a moment."],
    ["404", { status: 404 }, "This document no longer exists."],
    ["403", { status: 403 }, "You don't have permission to do that in Ada's workspace. Your role may have changed."],
    ["anything else", { status: 500 }, "Parsing wasn't started. Try again."],
  ];
  it.each(cases)("%s shows its toast and refetches the list", async (_name, forced, copy) => {
    renderTable();
    await screen.findByTestId("documents-table");
    server.forced[`POST ${PARSE_URL}`] = { message: "no", ...forced };
    const before = listCalls().length;
    await userEvent.click(within(rowOf(1)).getByTestId("document-parse"));
    expect(await screen.findByText(copy)).toBeInTheDocument();
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(before));
    expect(rowOf(1)).toHaveAttribute("data-run", "0");
  });

  it("says nothing for 409 already_running and refetches", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    server.forced[`POST ${PARSE_URL}`] = { status: 409, message: "busy", reason: "already_running" };
    const before = listCalls().length;
    await userEvent.click(within(rowOf(1)).getByTestId("document-parse"));
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(before));
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("shows the cancel fallback when a cancel fails", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1" })];
    renderTable();
    await screen.findByTestId("documents-table");
    server.forced[`POST ${PARSE_URL}`] = { status: 500, message: "x" };
    await userEvent.click(within(rowOf(1)).getByTestId("document-cancel"));
    expect(await screen.findByText("Parsing wasn't cancelled. Try again.")).toBeInTheDocument();
  });
});

describe("Parse again (D-03, D-04, D-09)", () => {
  it("sends the request without confirm_replace first, and a finished document opens the dialog with the server's counts", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 6 })];
    setFileExtra(server, documentRow(1).id, { editedCount: 2, manualCount: 1 });
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-more"));
    await userEvent.click(await screen.findByTestId("document-menu-reparse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(sent(PARSE_URL)).toEqual([{ doc_ids: [documentRow(1).id], run: "1" }]);
    expect(within(dialog).getByTestId("reparse-chunks")).toHaveTextContent("6");
    expect(within(dialog).getByTestId("reparse-edited")).toHaveTextContent("2");
    expect(within(dialog).getByTestId("reparse-manual")).toHaveTextContent("1");
  });

  it("starts at once for a failed or cancelled document with no edits", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "4", chunk_num: 3 }), documentRow(2, { run: "2" })];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(2)).getByTestId("document-reparse"));
    await waitFor(() => expect(rowOf(2)).toHaveAttribute("data-run", "1"));
    expect(screen.queryByTestId("reparse-dialog")).toBeNull();
    await userEvent.click(within(rowOf(1)).getByTestId("document-reparse"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    expect(screen.queryByTestId("reparse-dialog")).toBeNull();
  });

  it("opens the dialog for a failed document that has an edited chunk", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "4", chunk_num: 3 })];
    setFileExtra(server, documentRow(1).id, { editedCount: 1 });
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-reparse"));
    expect(await screen.findByTestId("reparse-dialog")).toBeInTheDocument();
    expect(rowOf(1)).toHaveAttribute("data-run", "4");
  });
});

describe("The 'In search' switch (D-10, D-26)", () => {
  it("waits for the server, then shows the server's value", async () => {
    let release: () => void = () => {};
    server.holds[`POST ${STATUS_URL}`] = new Promise<void>((resolve) => (release = resolve));
    renderTable();
    await screen.findByTestId("documents-table");
    const switchInput = within(rowOf(1)).getByRole("switch", { name: "Include report-01.pdf in search" });
    expect(switchInput).toBeChecked();
    await userEvent.click(switchInput);
    await waitFor(() => expect(switchInput).toHaveAttribute("aria-busy", "true"));
    expect(switchInput).toBeChecked();
    release();
    await waitFor(() => expect(switchInput).not.toBeChecked());
    expect(switchInput).not.toHaveAttribute("aria-busy");
    expect(sent(STATUS_URL)).toEqual([{ doc_ids: [documentRow(1).id], status: "0" }]);
    expect(within(rowOf(1)).getByText("Off")).toBeInTheDocument();
  });

  it("keeps the previous value and shows a toast when the change fails", async () => {
    renderTable();
    await screen.findByTestId("documents-table");
    server.forced[`POST ${STATUS_URL}`] = { status: 500, message: "x" };
    const switchInput = within(rowOf(1)).getByRole("switch");
    await userEvent.click(switchInput);
    expect(await screen.findByText("The search setting wasn't changed. Try again.")).toBeInTheDocument();
    expect(switchInput).toBeChecked();
  });
});

describe("Selection and the selection bar (D-01)", () => {
  it("has a header checkbox that selects the qualifying rows of the page and is indeterminate when partial", async () => {
    setFileExtra(server, documentRow(3).id, { parseable: false });
    renderTable();
    await screen.findByTestId("documents-table");
    const all = screen.getByRole("checkbox", { name: "Select all on this page" }) as HTMLInputElement;
    await userEvent.click(within(rowOf(1)).getByRole("checkbox", { name: "Select report-01.pdf" }));
    expect(all.indeterminate).toBe(true);
    await userEvent.click(all);
    expect(screen.getAllByTestId("document-select").filter((c) => (c as HTMLInputElement).checked)).toHaveLength(2);
    expect(screen.getByTestId("selection-count")).toHaveTextContent("2 documents selected");
    expect(all.checked).toBe(true);
    await userEvent.click(all);
    expect(screen.queryByTestId("selection-bar")).toBeNull();
  });

  it("counts parse and cancel from the selected rows and sends one request with all ids", async () => {
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2), documentRow(3, { run: "1", progress: 0.5 })];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("documents-select-all"));
    const bar = screen.getByRole("toolbar", { name: "Selected documents" });
    expect(within(bar).getByTestId("selection-count")).toHaveTextContent("3 documents selected");
    expect(within(bar).getByTestId("selection-parse")).toHaveTextContent("Parse 2 documents");
    expect(within(bar).getByTestId("selection-cancel")).toHaveTextContent("Cancel parsing for 1 document");
    await userEvent.click(within(bar).getByTestId("selection-parse"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "1"));
    expect(sent(PARSE_URL)).toEqual([{ doc_ids: [documentRow(1).id, documentRow(2).id], run: "1" }]);
    await waitFor(() => expect(screen.queryByTestId("selection-bar")).toBeNull());
  });

  it("cancels the running selection in one request", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1" }), documentRow(2, { run: "1" })];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("documents-select-all"));
    expect(screen.queryByTestId("selection-parse")).toBeNull();
    await userEvent.click(screen.getByTestId("selection-cancel"));
    await waitFor(() => expect(rowOf(1)).toHaveAttribute("data-run", "2"));
    expect(sent(PARSE_URL)).toEqual([{ doc_ids: [documentRow(1).id, documentRow(2).id], run: "2" }]);
  });

  it("opens the several-documents dialog when the server refuses, and clears the selection after a confirmed replace", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 4 }), documentRow(2, { run: "3", chunk_num: 2 }), documentRow(3)];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(screen.getByTestId("documents-select-all"));
    await userEvent.click(screen.getByTestId("selection-parse"));
    const dialog = await screen.findByTestId("reparse-dialog");
    expect(within(dialog).getByRole("heading", { name: "Parse 3 documents again?" })).toBeInTheDocument();
    expect(within(dialog).getByTestId("reparse-chunks")).toHaveTextContent("6");
    expect(server.callsTo("POST", PARSE_URL)).toHaveLength(1);
    await userEvent.click(within(dialog).getByTestId("reparse-confirm"));
    await waitFor(() => expect(screen.queryByTestId("reparse-dialog")).toBeNull());
    expect(sent(PARSE_URL)[1]).toMatchObject({ confirm_replace: true });
    await waitFor(() => expect(screen.queryByTestId("selection-bar")).toBeNull());
    expect(rowOf(1)).toHaveAttribute("data-run", "1");
  });

  it("keeps the selection through a polled refetch and drops a row that disappeared", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "1", progress: 0.1 }), documentRow(2), documentRow(3)];
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(2)).getByTestId("document-select"));
    await userEvent.click(within(rowOf(3)).getByTestId("document-select"));
    expect(screen.getByTestId("selection-count")).toHaveTextContent("2 documents selected");
    act(() => advanceParse(server, documentRow(1).id, { run: "1", progress: 0.6, message: "next" }));
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-progress")).toHaveTextContent("60%"), { timeout: 5000 });
    expect(screen.getByTestId("selection-count")).toHaveTextContent("2 documents selected");
    server.documents[DATASET_ID] = (server.documents[DATASET_ID] ?? []).filter((d) => d.id !== documentRow(3).id);
    act(() => advanceParse(server, documentRow(1).id, { run: "1", progress: 0.7 }));
    await waitFor(() => expect(screen.getByTestId("selection-count")).toHaveTextContent("1 document selected"), { timeout: 5000 });
  }, 15000);

  it("clears the selection on a page change and with Clear selection", async () => {
    server.documents[DATASET_ID] = Array.from({ length: 25 }, (_, i) => documentRow(i + 1));
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-select"));
    await userEvent.click(screen.getByTestId("selection-clear"));
    expect(screen.queryByTestId("selection-bar")).toBeNull();
    await userEvent.click(within(rowOf(1)).getByTestId("document-select"));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 2");
    expect(screen.queryByTestId("selection-bar")).toBeNull();
  });
});
