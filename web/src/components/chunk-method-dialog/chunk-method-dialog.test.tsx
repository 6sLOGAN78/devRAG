import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ChunkMethodDialog } from "@/components/chunk-method-dialog";
import { DatasetActionsMenu } from "@/components/dataset-actions-menu";
import { Toaster } from "@/components/ui/sonner";
import { CHUNK_METHODS, GENERAL_METHOD } from "@/constants/chunk-methods";
import { SETTINGS_MODES } from "@/constants/failure-codes";
import type { SessionUser } from "@/interfaces/user";
import { registerQueryClient } from "@/services/http";
import { DATASET_ID, documentRow } from "@/test/dataset-server";
import { DOCS_URL, OWNER, actAs, renderTable, rowOf, sent, server, useFilesServer } from "@/test/files-harness";
import { refuseNextSettings } from "@/test/server-areas/document-settings";
import { setDatasetDefaults, setFileExtra } from "@/test/server-areas/files";
import { waitUntil } from "@/test/wait-until";

useFilesServer();

const MEMBER: SessionUser = { ...OWNER, id: "u4", nickname: "Dan", tenantId: "t4", tenantName: "Dan's workspace" };
const SERVER_METHOD = "retired-parser";
const detailUrl = (n: number) => `${DOCS_URL}/${documentRow(n).id}`;
const datasetUrl = `/api/v1/datasets/${DATASET_ID}`;

async function openDialog(n = 1) {
  const user = userEvent.setup();
  await user.click(within(rowOf(n)).getByTestId("document-more"));
  await user.click(await screen.findByTestId("document-menu-chunking"));
  const dialog = await screen.findByTestId("chunk-method-dialog");
  await within(dialog).findByTestId("chunk-method-form");
  return { user, dialog };
}

async function openFirst() {
  renderTable();
  await screen.findByTestId("documents-table");
  return openDialog(1);
}

/** The footer's Close button (the corner icon has the same name and comes first). */
function closeOf(dialog: HTMLElement): HTMLElement {
  return within(dialog).getAllByRole("button", { name: "Close" }).at(-1) as HTMLElement;
}

async function replace(user: ReturnType<typeof userEvent.setup>, input: HTMLElement, text: string) {
  await user.clear(input);
  await user.type(input, text);
}

describe("Chunking method dialog, document mode (UI-13, UI-14)", () => {
  it("adds 'Chunking method' to the menu of a row the caller may change, but not to a parsing row or a read-only caller", async () => {
    server.documents[DATASET_ID] = [documentRow(1), documentRow(2, { run: "1", progress: 0.2 })];
    renderTable();
    await screen.findByTestId("documents-table");
    const user = userEvent.setup();
    await user.click(within(rowOf(1)).getByTestId("document-more"));
    expect(await screen.findByTestId("document-menu-chunking")).toHaveTextContent("Chunking method");
    await user.keyboard("{Escape}");
    await user.click(within(rowOf(2)).getByTestId("document-more"));
    await screen.findByTestId("document-menu-chunks");
    expect(screen.queryByTestId("document-menu-chunking")).toBeNull();
  });

  it("leaves the item out for a member who may not change the document", async () => {
    actAs(MEMBER, "normal", "u1");
    renderTable();
    await screen.findByTestId("documents-table");
    await userEvent.click(within(rowOf(1)).getByTestId("document-more"));
    await screen.findByTestId("document-menu-chunks");
    expect(screen.queryByTestId("document-menu-chunking")).toBeNull();
  });

  it("opens with the document's name, its description and its stored values", async () => {
    setFileExtra(server, documentRow(1).id, { chunkTokenNum: 256, overlappedPercent: 10 });
    const { dialog } = await openFirst();
    expect(within(dialog).getByRole("heading", { name: 'Chunking method for "report-01.pdf"' })).toBeInTheDocument();
    expect(within(dialog).getByText("How this document is split into chunks the next time it is parsed.")).toBeInTheDocument();
    expect(within(dialog).getByTestId("field-chunk-size")).toHaveValue(256);
    expect(within(dialog).getByTestId("field-delimiters")).toHaveValue("\\n!?;。；！？");
    expect(within(dialog).getByTestId("field-overlap")).toHaveValue(10);
  });

  it("lists all fourteen implemented methods in documentation order", async () => {
    const { dialog } = await openFirst();
    const radios = within(dialog).getAllByRole("radio");
    expect(radios).toHaveLength(14);
    expect(radios.filter((radio) => radio.hasAttribute("disabled"))).toHaveLength(0);
    expect(radios.map((radio) => radio.getAttribute("data-testid"))).toEqual(CHUNK_METHODS.map((id) => `chunk-method-option-${id}`));
    expect(screen.getByTestId(`chunk-method-option-${GENERAL_METHOD}`)).toBeChecked();
    const group = within(dialog).getByTestId("chunk-method-group");
    expect(within(group).queryByText("Available in a later release")).toBeNull();
    expect(within(group).getByText("Choose an available method for the next parse.")).toBeInTheDocument();
    for (const title of ["General", "Q&A", "Paper", "Book", "Laws", "Presentation", "Tables", "Manual"]) expect(within(group).getByText(title)).toBeInTheDocument();
    expect(within(group).getByText("Tag")).toBeInTheDocument();
  });

  it("offers off-by-default enrichment controls and omits unchanged values", async () => {
    const { dialog, user } = await openFirst();
    expect(within(dialog).getByTestId("field-auto-keywords")).toHaveValue(0);
    expect(within(dialog).getByTestId("field-auto-questions")).toHaveValue(0);
    await replace(user, within(dialog).getByTestId("field-chunk-size"), "300");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(JSON.stringify(sent(detailUrl(1), "PATCH")[0])).not.toMatch(/layout|keyword|question/);
  });

  it("keeps Save settings aria-disabled until something changed", async () => {
    const { dialog, user } = await openFirst();
    const submit = within(dialog).getByTestId("chunk-method-submit");
    expect(submit).toHaveAttribute("aria-disabled", "true");
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    expect(submit).not.toHaveAttribute("aria-disabled");
  });

  it("saves bounded generation counts and reopens them", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-auto-keywords"), "3");
    await replace(user, within(dialog).getByTestId("field-auto-questions"), "2");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toEqual([{parser_config:{auto_keywords:3,auto_questions:2}}]));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const {dialog:reopened} = await openDialog(1);
    expect(within(reopened).getByTestId("field-auto-keywords")).toHaveValue(3);
    expect(within(reopened).getByTestId("field-auto-questions")).toHaveValue(2);
  });

  it("sends only the changed keys, toasts, closes and returns focus to the row's menu button", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-chunk-size"), "300");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await screen.findByText("Chunking settings saved")).toBeInTheDocument();
    expect(sent(detailUrl(1), "PATCH")).toEqual([{ parser_config: { chunk_token_num: 300 } }]);
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-more")).toHaveFocus());
  });

  it("types a line break and a tab as \\n and \\t and sends the real characters", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-delimiters"), "\\t;\\n");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_config: { delimiter: "\t;\n" } });
  });

  it("preserves an explicitly stored backend when another field changes", async () => {
    setFileExtra(server, documentRow(1).id, { layoutRecognize: "docling" });
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-chunk-size"), "300");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(sent(detailUrl(1), "PATCH")).toEqual([{ parser_config: { chunk_token_num: 300 } }]);
    const next = await openDialog(1);
    expect(within(next.dialog).getByRole("checkbox", { name: "Use layout analysis" })).toBeChecked();
  });

  it("saves layout off and restores the switch when reopened", async () => {
    const { dialog, user } = await openFirst();
    await user.click(within(dialog).getByRole("checkbox", { name: "Use layout analysis" }));
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(sent(detailUrl(1), "PATCH")).toEqual([{ parser_config: { layout_recognize: false } }]);
    const next = await openDialog(1);
    expect(within(next.dialog).getByRole("checkbox", { name: "Use layout analysis" })).not.toBeChecked();
  });

  it("saves inclusive PDF ranges and restores them when reopened", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-page-ranges"), "2-4, 13");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(sent(detailUrl(1), "PATCH")).toEqual([{ parser_config: { pages: [[2, 4], [13, 13]] } }]);
    const next = await openDialog(1);
    expect(within(next.dialog).getByTestId("field-page-ranges")).toHaveValue("2-4, 13");
  });

  it("shows a saved delimiter escaped the next time the dialog opens", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-delimiters"), "\\n;");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const next = await openDialog(1);
    expect(within(next.dialog).getByTestId("field-delimiters")).toHaveValue("\\n;");
  });

  it("allows selecting Tag and sends the method for the next parse", async () => {
    const { dialog, user } = await openFirst();
    await user.click(screen.getByTestId("chunk-method-option-tag"));
    expect(screen.getByTestId("chunk-method-option-tag")).toBeChecked();
    expect(within(dialog).getByTestId("tag-settings-note")).toHaveTextContent("weighted tags");
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({parser_id:"tag"});
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const reopened = await openDialog(1);
    expect(within(reopened.dialog).getByTestId("chunk-method-option-tag")).toBeChecked();
  });

  it("selects no radio for a stored unbuilt method, warns, and needs General before saving", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { parser_id: SERVER_METHOD })];
    const { dialog, user } = await openFirst();
    expect(within(dialog).getAllByRole("radio").filter((radio) => (radio as HTMLInputElement).checked)).toHaveLength(0);
    expect(within(dialog).getByTestId("chunk-method-unavailable")).toHaveTextContent("This document is set to retired-parser, which isn't available yet. Choose General to parse it.");
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(within(dialog).getByTestId("chunk-method-submit")).toHaveAttribute("aria-disabled", "true");
    expect(sent(detailUrl(1), "PATCH")).toHaveLength(0);
    await user.click(screen.getByTestId(`chunk-method-option-${GENERAL_METHOD}`));
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: GENERAL_METHOD, parser_config: { overlapped_percent: 5 } });
  });

  it("notes that a parsed document keeps its chunks, in the singular and the plural", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 4 }), documentRow(2, { run: "3", chunk_num: 1 }), documentRow(3)];
    renderTable();
    await screen.findByTestId("documents-table");
    const first = await openDialog(1);
    expect(within(first.dialog).getByTestId("chunk-method-parsed-note")).toHaveTextContent("This document was parsed with its previous settings. Its 4 chunks stay as they are until you parse it again.");
    await first.user.click(closeOf(first.dialog));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const second = await openDialog(2);
    expect(within(second.dialog).getByTestId("chunk-method-parsed-note")).toHaveTextContent("Its 1 chunk stays as it is");
    await second.user.click(closeOf(second.dialog));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const third = await openDialog(3);
    expect(within(third.dialog).queryByTestId("chunk-method-parsed-note")).toBeNull();
  });

  it("saves a parsed document's settings without parsing anything", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { run: "3", chunk_num: 4 })];
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(server.callsTo("POST", `${DOCS_URL}/parse`)).toHaveLength(0);
    expect(server.documents[DATASET_ID]?.[0]?.chunk_num).toBe(4);
  });

  it("refuses a save for a document that started parsing meanwhile, with the 'being parsed' alert", async () => {
    const { dialog, user } = await openFirst();
    (server.documents[DATASET_ID] as { run: string }[])[0]!.run = "1";
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await within(dialog).findByTestId("chunk-method-error")).toHaveTextContent("This document is being parsed. Wait for it to finish or cancel parsing, then change the settings.");
  });

  it("places chunker_unavailable under Method", async () => {
    const { dialog, user } = await openFirst();
    refuseNextSettings(server, { status: 400, reason: "chunker_unavailable" });
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    const group = within(dialog).getByTestId("chunk-method-group");
    expect(await within(group).findByText("That method isn't available yet. Choose General.")).toBeInTheDocument();
    expect(within(dialog).queryByTestId("chunk-method-error")).toBeNull();
  });

  it.each([
    ["chunk_token_num", "field-chunk-size", "Enter a whole number from 1 to 8192."],
    ["overlapped_percent", "field-overlap", "Enter a whole number from 0 to 50."],
    ["delimiter", "field-delimiters", "Enter at least one delimiter."],
  ])("places parser_config_invalid for %s under its field", async (field, testId, message) => {
    const { dialog, user } = await openFirst();
    refuseNextSettings(server, { status: 400, reason: "parser_config_invalid", field });
    if (field === "delimiter") await replace(user, within(dialog).getByTestId(testId), "x");
    else await replace(user, within(dialog).getByTestId("field-chunk-size"), "300");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    const input = within(dialog).getByTestId(testId);
    const answer = await within(dialog).findByText(field === "delimiter" ? "Use 64 characters or fewer." : message);
    expect(answer.closest("[role='alert']")).not.toBeNull();
    expect(input.closest("div")).toContainElement(answer);
    expect(within(dialog).queryByTestId("chunk-method-error")).toBeNull();
  });

  it("shows the forbidden alert on a 403", async () => {
    const { dialog, user } = await openFirst();
    refuseNextSettings(server, { status: 403, reason: "forbidden" });
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await within(dialog).findByTestId("chunk-method-error")).toHaveTextContent("You don't have permission to do that in Ada's workspace.");
  });

  it("says the document is gone on a 404", async () => {
    const { dialog, user } = await openFirst();
    refuseNextSettings(server, { status: 404, reason: "not_found" });
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await within(dialog).findByTestId("chunk-method-error")).toHaveTextContent("This document no longer exists.");
  });

  it("falls back to a plain sentence on any other failure and lets the reader try again", async () => {
    const { dialog, user } = await openFirst();
    refuseNextSettings(server, { status: 500, reason: "internal" });
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await within(dialog).findByTestId("chunk-method-error")).toHaveTextContent("The settings weren't saved. Try again.");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(sent(detailUrl(1), "PATCH")).toHaveLength(2);
  });

  it("refuses an out-of-range size on the page and sends nothing", async () => {
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-chunk-size"), "9000");
    await user.type(within(dialog).getByTestId("field-chunk-size"), "{Enter}");
    expect(await within(dialog).findByText("Enter a whole number from 1 to 8192.")).toBeInTheDocument();
    expect(sent(detailUrl(1), "PATCH")).toHaveLength(0);
  });

  it("shows skeleton fields while loading and an error state with Try again when the load fails", async () => {
    server.forced[`GET ${detailUrl(1)}`] = { status: 500, message: "boom" };
    renderTable();
    await screen.findByTestId("documents-table");
    const user = userEvent.setup();
    await user.click(within(rowOf(1)).getByTestId("document-more"));
    await user.click(await screen.findByTestId("document-menu-chunking"));
    const dialog = await screen.findByTestId("chunk-method-dialog");
    expect(await within(dialog).findByRole("heading", { name: "Couldn't load the chunking settings" })).toBeInTheDocument();
    delete server.forced[`GET ${detailUrl(1)}`];
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByTestId("chunk-method-form")).toBeInTheDocument();
  });

  it("shows nothing of document A's failure when the dialog opens for document B (FE-04)", async () => {
    setFileExtra(server, documentRow(2).id, { chunkTokenNum: 256 });
    renderTable();
    await screen.findByTestId("documents-table");
    const first = await openDialog(1);
    refuseNextSettings(server, { status: 500, reason: "internal" });
    await replace(first.user, within(first.dialog).getByTestId("field-overlap"), "5");
    await first.user.click(within(first.dialog).getByTestId("chunk-method-submit"));
    await within(first.dialog).findByTestId("chunk-method-error");
    await first.user.click(closeOf(first.dialog));
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    const second = await openDialog(2);
    expect(within(second.dialog).queryByTestId("chunk-method-error")).toBeNull();
    expect(within(second.dialog).getByTestId("field-chunk-size")).toHaveValue(256);
    expect(within(second.dialog).getByTestId("field-overlap")).toHaveValue(0);
  });

  it("ignores Escape while a save is in flight", async () => {
    let release: () => void = () => {};
    server.holds[`PATCH ${detailUrl(1)}`] = new Promise<void>((resolve) => (release = resolve));
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitUntil(() => within(dialog).getByTestId("chunk-method-submit").getAttribute("aria-busy") === "true", { describe: "save in flight" });
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("chunk-method-dialog")).toBeInTheDocument();
    release();
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
  });

  it("sends one request when Save is pressed twice", async () => {
    let release: () => void = () => {};
    server.holds[`PATCH ${detailUrl(1)}`] = new Promise<void>((resolve) => (release = resolve));
    const { dialog, user } = await openFirst();
    await replace(user, within(dialog).getByTestId("field-overlap"), "5");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    release();
    await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
    expect(server.callsTo("PATCH", detailUrl(1))).toHaveLength(1);
  });

  it("hands focus back to the menu button when closed without saving", async () => {
    const { dialog, user } = await openFirst();
    await user.click(closeOf(dialog));
    await waitFor(() => expect(within(rowOf(1)).getByTestId("document-more")).toHaveFocus());
  });

  it("renders a hostile document name as text", async () => {
    server.documents[DATASET_ID] = [documentRow(1, { name: "<img src=x onerror=alert(1)>.pdf" })];
    const { dialog } = await openFirst();
    expect(dialog.querySelector("img")).toBeNull();
    expect(within(dialog).getByRole("heading")).toHaveTextContent('Chunking method for "<img src=x onerror=alert(1)>.pdf"');
  });
});

function DatasetHost({ withMenu = false }: { withMenu?: boolean }) {
  const [open, setOpen] = useState(!withMenu);
  return (
    <>
      {withMenu ? <DatasetActionsMenu name="Reports" onSettings={() => {}} onDelete={() => {}} onChunking={() => setOpen(true)} /> : null}
      <ChunkMethodDialog target={{ mode: SETTINGS_MODES.dataset, datasetId: DATASET_ID, tenantId: "t1", name: "Reports" }} open={open} onOpenChange={setOpen} />
    </>
  );
}

function renderDataset(withMenu = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  render(
    <QueryClientProvider client={client}>
      <DatasetHost withMenu={withMenu} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("Chunking method dialog, dataset default mode", () => {
  it("shows the default title and description with the dataset's stored values", async () => {
    setDatasetDefaults(server, DATASET_ID, { chunkTokenNum: 400, overlappedPercent: 20 });
    renderDataset();
    const dialog = await screen.findByTestId("chunk-method-dialog");
    await within(dialog).findByTestId("chunk-method-form");
    expect(within(dialog).getByRole("heading", { name: "Default chunking method" })).toBeInTheDocument();
    expect(within(dialog).getByText("Applied to documents uploaded from now on. Documents already in this dataset keep their own settings.")).toBeInTheDocument();
    expect(within(dialog).getByTestId("field-chunk-size")).toHaveValue(400);
    expect(within(dialog).getByTestId("field-overlap")).toHaveValue(20);
    expect(within(dialog).queryByTestId("chunk-method-parsed-note")).toBeNull();
  });

  it("saves through the dataset update route with only the changed keys", async () => {
    renderDataset();
    const dialog = await screen.findByTestId("chunk-method-dialog");
    await within(dialog).findByTestId("chunk-method-form");
    const user = userEvent.setup();
    await replace(user, within(dialog).getByTestId("field-chunk-size"), "300");
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await screen.findByText("Chunking settings saved")).toBeInTheDocument();
    const calls = server.callsTo("PUT", datasetUrl).map((call) => JSON.parse(String(call.data)) as Record<string, unknown>);
    expect(calls).toEqual([{ parser_config: { chunk_token_num: 300 } }]);
    expect(server.callsTo("PATCH", detailUrl(1))).toHaveLength(0);
  });

  it("uses the dataset wording for a stored unbuilt default and for a vanished dataset", async () => {
    setDatasetDefaults(server, DATASET_ID, { parserId: SERVER_METHOD });
    renderDataset();
    const dialog = await screen.findByTestId("chunk-method-dialog");
    await within(dialog).findByTestId("chunk-method-form");
    expect(within(dialog).getByTestId("chunk-method-unavailable")).toHaveTextContent("The default method is set to retired-parser, which isn't available yet. Choose General.");
    const user = userEvent.setup();
    await user.click(screen.getByTestId(`chunk-method-option-${GENERAL_METHOD}`));
    refuseNextSettings(server, { status: 404, reason: "not_found" });
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    expect(await within(dialog).findByTestId("chunk-method-error")).toHaveTextContent("This dataset no longer exists, or it isn't shared with you anymore.");
  });

  it("opens from the dataset actions menu item 'Default chunking method'", async () => {
    renderDataset(true);
    const user = userEvent.setup();
    expect(screen.queryByTestId("chunk-method-dialog")).toBeNull();
    await user.click(screen.getByTestId("dataset-actions"));
    await user.click(await screen.findByTestId("dataset-menu-chunking"));
    const dialog = await screen.findByTestId("chunk-method-dialog");
    expect(await within(dialog).findByRole("heading", { name: "Default chunking method" })).toBeInTheDocument();
  });

  it("leaves the menu item out unless the owner passes a handler", async () => {
    render(<DatasetActionsMenu name="Reports" onSettings={() => {}} onDelete={() => {}} />);
    await userEvent.click(screen.getByTestId("dataset-actions"));
    await screen.findByTestId("dataset-menu-settings");
    expect(screen.queryByTestId("dataset-menu-chunking")).toBeNull();
  });
});


it("saves and reopens One document without losing common settings", async () => {
  const {dialog,user} = await openFirst();
  await user.click(within(dialog).getByTestId("chunk-method-option-one"));
  expect(within(dialog).getByTestId("one-document-settings")).toBeInTheDocument();
  expect(within(dialog).getByTestId("field-chunk-size")).toBeDisabled();
  expect(within(dialog).getByTestId("field-page-ranges")).toBeEnabled();
  await user.click(within(dialog).getByTestId("chunk-method-submit"));
  await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
  expect(sent(detailUrl(1), "PATCH")[0]).toMatchObject({parser_id:"one"});
  await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
  const reopened = await openDialog();
  expect(within(reopened.dialog).getByTestId("chunk-method-option-one")).toBeChecked();
});

it("saves the implemented Manual method and restores it", async () => {
  const {dialog,user}=await openFirst();
  await user.click(within(dialog).getByTestId("chunk-method-option-manual"));
  await user.click(within(dialog).getByTestId("chunk-method-submit"));
  await waitFor(() => expect(sent(detailUrl(1),"PATCH")).toHaveLength(1));
  expect(sent(detailUrl(1),"PATCH")[0]).toMatchObject({parser_id:"manual"});
  await waitFor(() => expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
  const reopened=await openDialog();
  expect(within(reopened.dialog).getByTestId("chunk-method-option-manual")).toBeChecked();
});

it("saves Q&A and explains that a pair stays together", async () => {
 const {dialog,user}=await openFirst();
 await user.click(within(dialog).getByTestId("chunk-method-option-qa"));
 expect(within(dialog).getByTestId("qa-pair-settings")).toBeInTheDocument();
 expect(within(dialog).getByTestId("field-chunk-size")).toBeDisabled();
 await user.click(within(dialog).getByTestId("chunk-method-submit"));
 await waitFor(() => expect(sent(detailUrl(1),"PATCH")).toHaveLength(1));
 expect(sent(detailUrl(1),"PATCH")[0]).toMatchObject({parser_id:"qa"});
});


describe("Book chapter controls", () => {
  it("saves Book with size control and explains chapter order without ignored split controls", async () => {
    const { user, dialog } = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-book");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("book-settings-note")).toHaveTextContent("EPUB spine order");
    expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
    expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: "book" });
  });
});

describe("Paper section controls", () => {
  it("saves Paper with size control and explains section boundaries without ignored split controls", async () => {
    const { user, dialog } = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-paper");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("paper-settings-note")).toHaveTextContent("Abstract, Introduction, Methods and References");
    expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
    expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: "paper" });
  });
});

describe("Laws section controls", () => {
  it("saves Laws with size control and explains section boundaries without ignored split controls", async () => {
    const { user, dialog } = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-laws");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("laws-settings-note")).toHaveTextContent("chapters, sections, articles and items");
    expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
    expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: "laws" });
  });
});

describe("Presentation section controls", () => {
  it("saves Presentation with size control and explains section boundaries without ignored split controls", async () => {
    const { user, dialog } = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-presentation");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("presentation-settings-note")).toHaveTextContent("Keeps each slide separate");
    expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
    expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: "presentation" });
  });
});

describe("Table section controls", () => {
  it("saves Table with size control and explains section boundaries without ignored split controls", async () => {
    const { user, dialog } = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-table");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("table-settings-note")).toHaveTextContent("Keeps each data row with its table title and column headers");
    expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
    expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
    expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(() => expect(sent(detailUrl(1), "PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1), "PATCH")[0]).toEqual({ parser_id: "table" });
  });
});


describe("Picture controls", () => {
  it("saves an explicit OCR-only Picture choice and explains the vision alternative", async () => {
    const {user,dialog} = await openFirst();
    const option = within(dialog).getByTestId("chunk-method-option-picture");
    expect(option).not.toBeDisabled();
    await user.click(option);
    expect(within(dialog).getByTestId("picture-settings-note")).toHaveTextContent("vision model");
    await user.click(within(dialog).getByTestId("field-picture-ocr-only"));
    expect(within(dialog).getByTestId("field-image-model")).toBeDisabled();
    await user.click(within(dialog).getByTestId("chunk-method-submit"));
    await waitFor(()=>expect(sent(detailUrl(1),"PATCH")).toHaveLength(1));
    expect(sent(detailUrl(1),"PATCH")[0]).toEqual({parser_id:"picture",parser_config:{picture_ocr_only:true}});
  });
});

it("saves Email with envelope guidance and an effective body budget", async () => {
  const user=userEvent.setup();const {dialog}=await openFirst();
  await user.click(within(dialog).getByTestId("chunk-method-option-email"));
  expect(within(dialog).getByTestId("email-settings-note")).toHaveTextContent("From, To, Subject and Date");
  expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
  expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
  expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
  await user.click(within(dialog).getByTestId("chunk-method-submit"));
  await waitFor(()=>expect(sent(detailUrl(1),"PATCH")).toHaveLength(1));
  expect(sent(detailUrl(1),"PATCH")[0]).toEqual({parser_id:"email"});
});

it("saves explicit Resume model inference and restores its controls without parsing", async () => {
  const {dialog,user}=await openFirst();
  await user.click(within(dialog).getByTestId("chunk-method-option-resume"));
  expect(within(dialog).getByTestId("resume-settings-note")).toHaveTextContent("Missing values stay absent");
  expect(within(dialog).getByTestId("field-resume-use-model")).not.toBeChecked();
  expect(within(dialog).getByTestId("field-resume-model")).toBeDisabled();
  expect(within(dialog).getByTestId("field-delimiters")).toBeDisabled();
  expect(within(dialog).getByTestId("field-overlap")).toBeDisabled();
  expect(within(dialog).getByTestId("field-chunk-size")).not.toBeDisabled();
  await user.click(within(dialog).getByTestId("field-resume-use-model"));
  expect(within(dialog).getByTestId("field-resume-model")).not.toBeDisabled();
  await user.click(within(dialog).getByTestId("chunk-method-submit"));
  await waitFor(()=>expect(screen.queryByTestId("chunk-method-dialog")).toBeNull());
  expect(sent(detailUrl(1),"PATCH")[0]).toEqual({parser_id:"resume",parser_config:{resume_use_model:true}});
  const next=await openDialog(1);
  expect(within(next.dialog).getByTestId("field-resume-use-model")).toBeChecked();
});
