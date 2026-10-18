import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ChunkNotices } from "./chunk-notices";
import { DocumentEmpty, InspectorNotFound, NoPreviewNote, typeLabelOf } from "./inspector-states";

type EmptyDocument = Parameters<typeof DocumentEmpty>[0]["document"];

const doc = (over: Partial<EmptyDocument> = {}): EmptyDocument => ({
  name: "report-01.pdf",
  suffix: "pdf",
  run: "0",
  parseable: true,
  progress: 0,
  progressMessage: "",
  error: null,
  chunkCount: 0,
  lastLogId: null,
  ...over,
});

function empty(document: EmptyDocument, over: Partial<Parameters<typeof DocumentEmpty>[0]> = {}) {
  const handlers = { onParse: vi.fn(), onCancel: vi.fn(), onDetails: vi.fn() };
  render(
    <MemoryRouter>
      <DocumentEmpty document={document} canChange busy={false} {...handlers} {...over} />
    </MemoryRouter>,
  );
  return handlers;
}

describe("Document states without chunks (UI-SPEC States)", () => {
  it("offers 'Parse document' as the one primary button for a document that was never parsed", async () => {
    const { onParse } = empty(doc());
    expect(screen.getByRole("heading", { name: "No chunks yet" })).toBeInTheDocument();
    expect(screen.getByText("Parse this document to split it into searchable chunks.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Parse document" }));
    expect(onParse).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("chunk-empty-parse")).toBe(screen.getByRole("button", { name: "Parse document" }));
  });

  it("explains to a read-only caller who may parse, and offers nothing", () => {
    empty(doc(), { canChange: false });
    expect(screen.getByRole("heading", { name: "No chunks yet" })).toBeInTheDocument();
    expect(screen.getByText("This document hasn't been parsed yet. The person who uploaded it, the dataset's creator or a workspace admin can parse it.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps the button from firing twice while a request is in flight", () => {
    empty(doc(), { busy: true });
    expect(screen.getByTestId("chunk-empty-parse")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("chunk-empty-parse")).toHaveAttribute("aria-busy", "true");
  });

  it("says a type without a parser can be stored and downloaded only", () => {
    empty(doc({ parseable: false, suffix: "mp3" }));
    expect(screen.getByRole("heading", { name: "Parsing not available yet" })).toBeInTheDocument();
    expect(screen.getByText("MP3 files can be stored and downloaded, but they can't be parsed in this release.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Parse document" })).toBeNull();
  });

  it("shows progress and the latest message while parsing, with a cancel for a caller who may change it", async () => {
    const { onCancel } = empty(doc({ run: "1", progress: 0.456, progressMessage: "Reading page 4 of 9" }));
    expect(screen.getByRole("heading", { name: "Parsing in progress" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "45");
    expect(screen.getByTestId("chunk-empty")).toHaveTextContent("45%");
    expect(screen.getByText("Reading page 4 of 9")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel parsing" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("never shows 100 percent while parsing is still running", () => {
    empty(doc({ run: "1", progress: 0.996 }), { canChange: false });
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "99");
    expect(screen.queryByRole("button", { name: "Cancel parsing" })).toBeNull();
  });

  it("says why parsing failed with the reason sentence, 'Parse again' and a details link", async () => {
    const { onParse, onDetails } = empty(doc({ run: "4", error: { step: "embed", code: "provider_timeout", message: "x" }, lastLogId: "log1" }));
    expect(screen.getByRole("heading", { name: "Parsing failed" })).toBeInTheDocument();
    expect(screen.getByTestId("chunk-empty")).toHaveAttribute("data-kind", "failed");
    expect(screen.getByTestId("chunk-empty")).toHaveTextContent(/timed out/i);
    await userEvent.click(screen.getByRole("button", { name: "Parse again" }));
    expect(onParse).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Parsing details" }));
    expect(onDetails).toHaveBeenCalledTimes(1);
  });

  it("shows the server's plain message as text when the code is unknown", () => {
    empty(doc({ run: "4", error: { step: "parse", code: "something_new", message: "<b>Odd</b> failure" }, lastLogId: "log1" }));
    expect(screen.getByText("<b>Odd</b> failure")).toBeInTheDocument();
  });

  it("leaves 'Parse again' out for a read-only caller and the details link out without a run", () => {
    empty(doc({ run: "4", error: null }), { canChange: false });
    expect(screen.queryByRole("button", { name: "Parse again" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Parsing details" })).toBeNull();
  });

  it("says parsing was cancelled and that no chunks were indexed", async () => {
    const { onParse } = empty(doc({ run: "2" }));
    expect(screen.getByRole("heading", { name: "Parsing was cancelled" })).toBeInTheDocument();
    expect(screen.getByText("No chunks were indexed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Parse again" }));
    expect(onParse).toHaveBeenCalledTimes(1);
  });
});

describe("Notices, page not found and the no-preview note", () => {
  const notices = (over: Partial<Parameters<typeof ChunkNotices>[0]> = {}) => {
    const onDetails = vi.fn();
    render(<ChunkNotices readOnly={false} documentOff={false} parsing={false} partial={false} canOpenDetails onDetails={onDetails} {...over} />);
    return onDetails;
  };

  it("shows nothing when nothing applies", () => {
    notices();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows the four notices in order as polite info alerts", () => {
    notices({ readOnly: true, documentOff: true, parsing: true, partial: true });
    const shown = screen.getAllByRole("status");
    expect(shown.map((n) => n.getAttribute("data-testid"))).toEqual(["chunk-readonly-notice", "chunk-document-off-notice", "chunk-parsing-notice", "chunk-partial-notice"]);
    expect(shown[0]).toHaveTextContent("You can read these chunks. Only the person who uploaded this document, the dataset's creator and the workspace owner and admins can change them.");
    expect(shown[1]).toHaveTextContent("This document is switched off for search, so none of its chunks are returned. Each chunk keeps its own setting below and returns to search when the document is switched on.");
    expect(shown[2]).toHaveTextContent("This document is being parsed. Chunks appear here as they are indexed, and editing is paused until parsing ends.");
    expect(shown[3]).toHaveTextContent("Parsing did not finish, so this list is incomplete.");
  });

  it("opens the parsing details from the partly-indexed notice", async () => {
    const onDetails = notices({ partial: true });
    await userEvent.click(within(screen.getByTestId("chunk-partial-notice")).getByRole("button", { name: "Details" }));
    expect(onDetails).toHaveBeenCalledTimes(1);
  });

  it("leaves the link out when there is no run to show", () => {
    notices({ partial: true, canOpenDetails: false });
    expect(within(screen.getByTestId("chunk-partial-notice")).queryByRole("button")).toBeNull();
  });

  it("shows one identical not-found page with a single way out", () => {
    render(
      <MemoryRouter>
        <InspectorNotFound />
      </MemoryRouter>,
    );
    const page = screen.getByTestId("chunk-not-found");
    expect(within(page).getByRole("heading", { level: 1, name: "Document not found" })).toBeInTheDocument();
    expect(within(page).getByText("It may have been deleted, or it isn't shared with you.")).toBeInTheDocument();
    expect(within(page).getByRole("link", { name: "Back to datasets" })).toHaveAttribute("href", "/datasets");
  });

  it("names the type in the no-preview note and builds the label in one place", () => {
    render(<NoPreviewNote type="DOCX" />);
    expect(screen.getByTestId("no-preview-note")).toHaveTextContent("DOCX files have no page preview. Chunks are shown as the text that was read from the file.");
    expect(typeLabelOf("docx")).toBe("DOCX");
    expect(typeLabelOf("")).toBe("");
    expect(typeLabelOf(".md")).toBe("MD");
  });
});
