import { GENERAL_METHOD } from "@/constants/chunk-methods";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, CanceledError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { documentsQueryKey } from "@/hooks/use-document-request";
import { datasetQueryKey, datasetsKeyRoot } from "@/hooks/use-knowledge-request";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { FileUploadDialog } from ".";

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

const LIMITS = {
  maxFileBytes: 1024,
  maxFilesPerRequest: 3,
  maxDocuments: 10,
  allowedExtensions: ["pdf", "docx", "pptx", "xlsx", "txt", "md", "markdown", "csv", "json", "html", "htm", "epub", "jpg", "jpeg", "png", "mp3", "wav"],
};

interface Pending {
  config: InternalAxiosRequestConfig;
  name: string;
  aborted: boolean;
  resolve: (data: unknown) => void;
  reject: (error: unknown) => void;
}

const originalAdapter = http.defaults.adapter;
let pending: Pending[] = [];

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, status: number, message: string, reason?: string) {
  const response = { data: { code: status, message, data: reason ? { reason } : null }, status, statusText: String(status), headers: new AxiosHeaders(), config } as never;
  return new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response);
}

const adapter: AxiosAdapter = (config) => {
  if (config.url === "/api/v1/documents/upload") {
    return new Promise((resolve, reject) => {
      const sent = (config.data as FormData).get("file") as File;
      const entry: Pending = { config, name: sent.name, aborted: false, resolve: (data) => resolve(ok(config, data)), reject };
      config.signal?.addEventListener?.("abort", () => {
        entry.aborted = true;
        reject(new CanceledError(undefined, config));
      });
      pending.push(entry);
    });
  }
  if (config.url === "/v1/tenant/list") return Promise.resolve(ok(config, []));
  return Promise.reject(failure(config, 404, "not found"));
};

const documentDto = (name: string) => ({
  id: `id-${name}`,
  name,
  size: 10,
  type: "pdf",
  suffix: "pdf",
  run: "0",
  progress: 0,
  dataset_id: "kb1",
  created_by: "u1",
  parser_id: GENERAL_METHOD,
  chunk_num: 0,
  token_num: 0,
  create_time: 1,
  update_time: 2,
});

const entryFor = (name: string): Pending => {
  const found = pending.find((p) => p.name === name);
  if (!found) throw new Error(`no upload for ${name}; saw ${pending.map((p) => p.name).join(", ")}`);
  return found;
};
/** Lets the transport's promise chain reach the queue; microtasks only. */
const settle = async () => {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
};
const succeed = (name: string, savedAs = name) =>
  act(async () => {
    entryFor(name).resolve([documentDto(savedAs)]);
    await settle();
  });
const failWith = (name: string, error: unknown) =>
  act(async () => {
    entryFor(name).reject(error);
    await settle();
  });
const fail = (name: string, status: number, message = "", reason?: string) => failWith(name, failure(entryFor(name).config, status, message, reason));
const sendProgress = (name: string, loaded: number, total: number) => act(() => entryFor(name).config.onUploadProgress?.({ loaded, total } as never));

let lastModified = 1;
const makeFile = (name: string, size = 100) => new File([new Uint8Array(size)], name, { lastModified: (lastModified += 1) });

interface Item {
  file: File;
  directory?: boolean;
}
function transfer(items: Array<File | Item>, types: string[] = ["Files"]) {
  const list = items.map((entry) => ("file" in entry ? entry : { file: entry }));
  return {
    types,
    files: list.map((entry) => entry.file),
    items: list.map((entry) => ({ kind: "file", getAsFile: () => entry.file, webkitGetAsEntry: () => ({ isDirectory: entry.directory === true }) })),
  };
}

let client: QueryClient;
const onOpenChange = vi.fn();

function renderDialog(props: Partial<Parameters<typeof FileUploadDialog>[0]> = {}) {
  const view = render(
    <QueryClientProvider client={client}>
      <FileUploadDialog dataset={{ id: "kb1", name: "Reports", docNum: 3 }} limits={LIMITS} open onOpenChange={onOpenChange} {...props} />
    </QueryClientProvider>,
  );
  return view;
}

const zone = () => screen.getByTestId("upload-dropzone");
const submit = () => screen.getByTestId("upload-submit");
const live = () => screen.getByTestId("upload-live");
const dropFiles = (items: Array<File | Item>) => act(() => void fireEvent.drop(zone(), { dataTransfer: transfer(items) }));
const rowOf = (name: string) => {
  const found = screen.getAllByTestId("upload-row").find((r) => r.textContent?.includes(name));
  if (!found) throw new Error(`no row for ${name}`);
  return found;
};
const stateOf = (name: string) => within(rowOf(name)).getByTestId("upload-row-state").textContent;

beforeEach(() => {
  pending = [];
  onOpenChange.mockClear();
  http.defaults.adapter = adapter;
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  useUserStore.setState({ user: USER });
  useWorkspaceStore.getState().reset();
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("opening (UI-12)", () => {
  it("shows the title, description and the dropzone, with the primary disabled and focus on Choose files", async () => {
    renderDialog();
    expect(screen.getByRole("dialog", { name: "Upload files to Reports" })).toBeInTheDocument();
    expect(screen.getByTestId("upload-dialog")).toBeInTheDocument();
    expect(screen.getByText(/Up to 1 KB per file, 3 files at a time\./)).toBeInTheDocument();
    expect(zone()).toHaveAttribute("role", "group");
    expect(zone().className).toContain("border-dashed");
    expect(zone().className).toContain("min-h-40");
    expect(submit()).toHaveTextContent("Upload 0 files");
    expect(submit()).toHaveAttribute("aria-disabled", "true");
    await waitFor(() => expect(screen.getByTestId("upload-choose")).toHaveFocus());
  });

  it("gives the hidden input the extension list as its accept value", () => {
    renderDialog();
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    expect(input).toHaveAttribute("type", "file");
    expect(input.multiple).toBe(true);
    expect(input.accept).toBe(LIMITS.allowedExtensions.map((ext) => `.${ext}`).join(","));
  });

  it("falls back to the compiled-in limits when the dataset carries none", () => {
    renderDialog({ limits: null });
    expect(screen.getByText(/Up to 100 MB per file, 20 files at a time\./)).toBeInTheDocument();
  });

  it("queues the files that were dropped on the page behind it", () => {
    renderDialog({ initialFiles: [makeFile("first.pdf")] });
    expect(stateOf("first.pdf")).toBe("Ready to upload");
    expect(submit()).toHaveTextContent("Upload 1 file");
  });

  it("replaces the dropzone with an info alert when the dataset is full", () => {
    renderDialog({ dataset: { id: "kb1", name: "Reports", docNum: 10 } });
    expect(screen.queryByTestId("upload-dropzone")).toBeNull();
    expect(screen.getByText("This dataset already holds the maximum of 10 documents. Delete some before uploading more.")).toBeInTheDocument();
  });
});

describe("native drag and drop (no library)", () => {
  it("prevents default on dragenter and dragover only for a file drag, and shows the active state", () => {
    renderDialog();
    expect(fireEvent.dragEnter(zone(), { dataTransfer: transfer([], ["text/plain"]) })).toBe(true);
    expect(fireEvent.dragOver(zone(), { dataTransfer: transfer([], ["text/plain"]) })).toBe(true);
    expect(screen.queryByText("Drop to add files")).toBeNull();
    expect(fireEvent.dragEnter(zone(), { dataTransfer: transfer([makeFile("a.pdf")]) })).toBe(false);
    expect(fireEvent.dragOver(zone(), { dataTransfer: transfer([makeFile("a.pdf")]) })).toBe(false);
    expect(screen.getByText("Drop to add files")).toBeInTheDocument();
    expect(zone().className).toContain("border-solid");
    expect(zone().className).toContain("border-primary");
    expect(screen.queryByText("Drag files here, or")).toBeNull();
  });

  it("keeps the active state through nested enter and leave events (depth counter)", () => {
    renderDialog();
    const dt = transfer([makeFile("a.pdf")]);
    fireEvent.dragEnter(zone(), { dataTransfer: dt });
    fireEvent.dragEnter(zone(), { dataTransfer: dt });
    fireEvent.dragLeave(zone(), { dataTransfer: dt });
    expect(screen.getByText("Drop to add files")).toBeInTheDocument();
    fireEvent.dragLeave(zone(), { dataTransfer: dt });
    expect(screen.queryByText("Drop to add files")).toBeNull();
    expect(screen.getByText("Drag files here, or")).toBeInTheDocument();
  });

  it("adds the dropped files and ends the active state", () => {
    renderDialog();
    fireEvent.dragEnter(zone(), { dataTransfer: transfer([makeFile("a.pdf")]) });
    dropFiles([makeFile("a.pdf"), makeFile("b.txt")]);
    expect(screen.getAllByTestId("upload-row")).toHaveLength(2);
    expect(stateOf("a.pdf")).toBe("Ready to upload");
    expect(screen.queryByText("Drop to add files")).toBeNull();
    expect(submit()).toHaveTextContent("Upload 2 files");
    expect(submit()).not.toHaveAttribute("aria-disabled", "true");
  });

  it("prevents a file drag or drop that misses the zone from navigating the browser, and stops when the dialog closes", () => {
    const view = renderDialog();
    const dt = transfer([makeFile("a.pdf")]);
    expect(fireEvent.dragOver(window, { dataTransfer: dt })).toBe(false);
    expect(fireEvent.drop(window, { dataTransfer: dt })).toBe(false);
    expect(fireEvent.dragOver(window, { dataTransfer: transfer([], ["text/plain"]) })).toBe(true);
    view.rerender(
      <QueryClientProvider client={client}>
        <FileUploadDialog dataset={{ id: "kb1", name: "Reports", docNum: 3 }} limits={LIMITS} open={false} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );
    expect(fireEvent.dragOver(window, { dataTransfer: dt })).toBe(true);
    expect(fireEvent.drop(window, { dataTransfer: dt })).toBe(true);
  });

  it("opens the file picker from Choose files and adds what the input receives", async () => {
    const user = userEvent.setup();
    renderDialog();
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click").mockImplementation(() => undefined);
    await user.click(screen.getByTestId("upload-choose"));
    expect(click).toHaveBeenCalledTimes(1);
    await user.upload(input, makeFile("picked.pdf"));
    expect(stateOf("picked.pdf")).toBe("Ready to upload");
  });

  it("ignores the same file added twice (name, size and modified time)", () => {
    renderDialog();
    const same = makeFile("a.pdf");
    dropFiles([same]);
    dropFiles([same]);
    expect(screen.getAllByTestId("upload-row")).toHaveLength(1);
  });
});

describe("client checks and batch limits (D-11, D-12, D-13, D-28)", () => {
  it("lists a refused file with its reason and a Remove button, and never counts it", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([
      makeFile("x.gif"),
      makeFile("a.pdf.exe"),
      makeFile("noext"),
      makeFile("empty.pdf", 0),
      makeFile("big.pdf", 1536),
      makeFile(`${"n".repeat(252)}.pdf`),
      { file: makeFile("docs", 0), directory: true },
    ]);
    expect(stateOf("x.gif")).toBe(".gif files aren't supported.");
    expect(stateOf("a.pdf.exe")).toBe(".exe files aren't supported.");
    expect(stateOf("noext")).toBe("Files without an extension aren't supported.");
    expect(stateOf("empty.pdf")).toBe("This file is empty.");
    expect(stateOf("big.pdf")).toBe("This file is 1.5 KB. The limit is 1 KB per file.");
    expect(stateOf("n".repeat(252))).toBe("This file name is too long. Rename it to 255 characters or fewer.");
    expect(stateOf("docs")).toBe("Folders can't be uploaded. Add the files inside it instead.");
    expect(submit()).toHaveTextContent("Upload 0 files");
    await user.click(screen.getByRole("button", { name: "Remove x.gif" }));
    expect(screen.queryByText("x.gif")).toBeNull();
  });

  it("accepts jpg, jpeg and png and refuses webp, bmp and tiff", () => {
    renderDialog();
    dropFiles([makeFile("a.jpg"), makeFile("b.jpeg"), makeFile("c.png"), makeFile("d.webp"), makeFile("e.bmp"), makeFile("f.tiff")]);
    expect(stateOf("a.jpg")).toBe("Ready to upload");
    expect(stateOf("c.png")).toBe("Ready to upload");
    expect(stateOf("d.webp")).toBe(".webp files aren't supported.");
    expect(stateOf("e.bmp")).toBe(".bmp files aren't supported.");
    expect(stateOf("f.tiff")).toBe(".tiff files aren't supported.");
  });

  it("queues the first files up to the request limit and reports the rest once above the list", () => {
    renderDialog();
    dropFiles([makeFile("1.pdf"), makeFile("2.pdf"), makeFile("3.pdf"), makeFile("4.pdf"), makeFile("5.pdf")]);
    expect(screen.getAllByTestId("upload-row")).toHaveLength(3);
    expect(screen.getByTestId("upload-batch-notice")).toHaveTextContent("You can upload 3 files at a time. 2 files weren't added.");
    dropFiles([makeFile("6.pdf")]);
    expect(screen.getByTestId("upload-batch-notice")).toHaveTextContent("You can upload 3 files at a time. 1 file wasn't added.");
  });

  it("clears the batch notice on an add that needs none", () => {
    renderDialog();
    dropFiles([makeFile("1.pdf"), makeFile("2.pdf"), makeFile("3.pdf"), makeFile("4.pdf")]);
    expect(screen.getByTestId("upload-batch-notice")).toBeInTheDocument();
    act(() => void fireEvent.click(screen.getByRole("button", { name: "Remove 1.pdf" })));
    dropFiles([makeFile("5.pdf")]);
    expect(screen.queryByTestId("upload-batch-notice")).toBeNull();
  });

  it("queues files up to the dataset's remaining room and reports the rest", () => {
    renderDialog({ dataset: { id: "kb1", name: "Reports", docNum: 9 } });
    dropFiles([makeFile("1.pdf"), makeFile("2.pdf"), makeFile("3.pdf")]);
    expect(screen.getAllByTestId("upload-row")).toHaveLength(1);
    expect(screen.getByTestId("upload-batch-notice")).toHaveTextContent("This dataset can hold 10 documents and has 9. 2 files weren't added.");
  });
});

describe("uploading (UI-SPEC upload behaviour, Pitfall 8)", () => {
  it("uploads only after the primary is pressed: one POST per file, two in flight, no client timeout", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf"), makeFile("c.pdf")]);
    expect(pending).toHaveLength(0);
    await user.click(submit());
    expect(pending.map((p) => p.name)).toEqual(["a.pdf", "b.pdf"]);
    const config = pending[0]!.config;
    expect(config.params).toEqual({ dataset_id: "kb1" });
    expect(config.timeout).toBe(0);
    expect(config.data).toBeInstanceOf(FormData);
    expect(config.signal).toBeDefined();
    expect(submit()).toHaveTextContent("Uploading 0 of 3");
    expect(submit()).toHaveAttribute("aria-disabled", "true");
    expect(stateOf("c.pdf")).toBe("Ready to upload");
    await succeed("a.pdf");
    await waitFor(() => expect(pending.map((p) => p.name)).toEqual(["a.pdf", "b.pdf", "c.pdf"]));
  });

  it("shows progress capped below 100, then Finishing with a full bar until the server answers", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    await sendProgress("a.pdf", 50, 100);
    expect(stateOf("a.pdf")).toBe("50%");
    const bar = within(rowOf("a.pdf")).getByTestId("upload-row-progress");
    expect(bar).toHaveAttribute("role", "progressbar");
    expect(bar).toHaveAttribute("aria-label", "Upload progress for a.pdf");
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    await sendProgress("a.pdf", 999, 1000);
    expect(stateOf("a.pdf")).toBe("99%");
    await sendProgress("a.pdf", 1000, 1000);
    expect(stateOf("a.pdf")).toBe("Finishing");
    expect(within(rowOf("a.pdf")).getByTestId("upload-row-progress")).toHaveAttribute("aria-valuetext", "Finishing");
    expect(within(rowOf("a.pdf")).getByTestId("upload-row-progress")).toHaveAttribute("aria-valuenow", "100");
    expect(within(rowOf("a.pdf")).queryByTestId("upload-row-cancel")).toBeNull();
    await succeed("a.pdf");
    expect(stateOf("a.pdf")).toBe("Uploaded");
    expect(within(rowOf("a.pdf")).queryByTestId("upload-row-progress")).toBeNull();
  });

  it("shows an auto-renamed file as 'Uploaded as' and one info alert (D-14)", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("report.pdf"), makeFile("plain.pdf"), makeFile("other.pdf")]);
    await user.click(submit());
    await succeed("report.pdf", "report(1).pdf");
    await succeed("plain.pdf");
    expect(stateOf("report.pdf")).toBe("Uploaded as report(1).pdf");
    const notice = screen.getByTestId("upload-rename-notice");
    expect(notice).toHaveTextContent("1 file was renamed because a file with the same name was already in this dataset. Nothing was overwritten.");
    await waitFor(() => expect(pending.map((p) => p.name)).toContain("other.pdf"));
    await succeed("other.pdf", "other(1).pdf");
    expect(screen.getByTestId("upload-rename-notice")).toHaveTextContent("2 files were renamed because a file with the same name was already in this dataset.");
  });

  it("ends in Done, named 'Close upload dialog', focused, and never closes by itself", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf")]);
    await user.click(submit());
    await succeed("a.pdf");
    expect(submit()).toHaveTextContent("Uploading 1 of 2");
    await succeed("b.pdf");
    expect(submit()).toHaveTextContent("Done");
    expect(submit()).toHaveAccessibleName("Close upload dialog");
    expect(screen.getByRole("button", { name: "Close upload dialog" })).toBe(submit());
    await waitFor(() => expect(submit()).toHaveFocus());
    expect(onOpenChange).not.toHaveBeenCalled();
    await user.click(submit());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("refreshes the document list and both dataset keys after each uploaded file (TEN-13)", async () => {
    const user = userEvent.setup();
    const keys = [documentsQueryKey("t1", "kb1", 1, ""), [...datasetsKeyRoot("t1"), 1, ""], datasetQueryKey("t1", "kb1"), documentsQueryKey("t2", "kb1", 1, "")];
    for (const key of keys) client.setQueryData(key, { seeded: true });
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    expect(client.getQueryState(keys[0]!)?.isInvalidated).toBe(false);
    await succeed("a.pdf");
    await waitFor(() => expect(client.getQueryState(keys[0]!)?.isInvalidated).toBe(true));
    expect(client.getQueryState(keys[1]!)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys[2]!)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys[3]!)?.isInvalidated).toBe(false);
  });

  it("renders file names as text, never as markup (T-03-24-01)", async () => {
    const hostile = "<img src=x onerror=alert(1)>.pdf";
    const { container } = renderDialog();
    dropFiles([makeFile(hostile)]);
    expect(container.ownerDocument.querySelector("img")).toBeNull();
    expect(screen.getByTestId("upload-list")).toHaveTextContent(hostile);
  });
});

describe("server answers per file", () => {
  async function uploadOne(name = "a.pdf", extra: string[] = []) {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile(name), ...extra.map((n) => makeFile(n))]);
    await user.click(submit());
    return user;
  }

  it("HTTP 400 shows the server message and offers Try again", async () => {
    await uploadOne();
    await fail("a.pdf", 400, "unsupported file type", "unsupported_type");
    expect(stateOf("a.pdf")).toBe("unsupported file type");
    expect(within(rowOf("a.pdf")).getByRole("button", { name: "Try uploading a.pdf again" })).toHaveTextContent("Try again");
  });

  it("HTTP 400 without a message shows the generic refusal", async () => {
    await uploadOne();
    await fail("a.pdf", 400, "");
    expect(stateOf("a.pdf")).toBe("The server didn't accept this file.");
  });

  it("HTTP 413 shows the size message with the limit", async () => {
    await uploadOne();
    await fail("a.pdf", 413, "payload too large");
    expect(stateOf("a.pdf")).toBe("This file is larger than the 1 KB limit.");
  });

  it("HTTP 5xx and a lost connection show the retryable messages", async () => {
    await uploadOne("a.pdf", ["b.pdf"]);
    await fail("a.pdf", 503, "busy", "busy");
    expect(stateOf("a.pdf")).toBe("The server couldn't store this file. Try again.");
    await failWith("b.pdf", new AxiosError("Network Error", "ERR_NETWORK", entryFor("b.pdf").config));
    expect(stateOf("b.pdf")).toBe("The connection was lost. Try again.");
  });

  it("a limit answer fails the remaining ready rows with the same message", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf"), makeFile("c.pdf")]);
    await user.click(submit());
    await fail("a.pdf", 400, "This dataset is full.", "dataset_limit");
    expect(stateOf("a.pdf")).toBe("This dataset is full.");
    expect(stateOf("c.pdf")).toBe("This dataset is full.");
    expect(pending.map((p) => p.name)).toEqual(["a.pdf", "b.pdf"]);
  });

  it("HTTP 404 shows a dialog-level alert, cancels the ready rows and stops", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf"), makeFile("c.pdf")]);
    await user.click(submit());
    await fail("a.pdf", 404, "not found");
    expect(screen.getByTestId("upload-fatal")).toHaveTextContent("This dataset no longer exists or isn't shared with you. Nothing more was uploaded.");
    expect(screen.getByTestId("upload-fatal")).toHaveAttribute("role", "alert");
    expect(stateOf("c.pdf")).toBe("Cancelled");
    expect(pending).toHaveLength(2);
  });

  it("HTTP 403 shows the permission alert", async () => {
    await uploadOne();
    await fail("a.pdf", 403, "forbidden");
    expect(screen.getByTestId("upload-fatal")).toHaveTextContent("You don't have permission to upload to this dataset.");
  });

  it("Try again uploads the file again", async () => {
    const user = await uploadOne();
    await fail("a.pdf", 500, "boom");
    await user.click(screen.getByRole("button", { name: "Try uploading a.pdf again" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(stateOf("a.pdf")).toBe("0%");
    pending[1]!.resolve([documentDto("a.pdf")]);
    await waitFor(() => expect(stateOf("a.pdf")).toBe("Uploaded"));
  });

  it("ends with Done even when a file failed, keeping Try again", async () => {
    await uploadOne("a.pdf", ["b.pdf"]);
    await succeed("a.pdf");
    await fail("b.pdf", 500, "boom");
    expect(submit()).toHaveTextContent("Done");
    expect(screen.getByRole("button", { name: "Try uploading b.pdf again" })).toBeInTheDocument();
  });
});

describe("cancelling and closing", () => {
  it("cancels one running upload through its own button and aborts the request", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    await user.click(screen.getByRole("button", { name: "Cancel upload of a.pdf" }));
    expect(entryFor("a.pdf").aborted).toBe(true);
    await waitFor(() => expect(stateOf("a.pdf")).toBe("Cancelled"));
    expect(screen.getByRole("button", { name: "Try uploading a.pdf again" })).toBeInTheDocument();
  });

  it("closes at once when nothing is uploading: Escape, the corner X and the footer Close", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(screen.queryByTestId("upload-stop-dialog")).toBeNull();
    onOpenChange.mockClear();
    await user.click(screen.getByTestId("upload-close"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    onOpenChange.mockClear();
    const corner = screen.getAllByRole("button", { name: "Close" }).find((b) => b !== screen.getByTestId("upload-close"));
    await user.click(corner!);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it.each([
    ["Escape", async (user: ReturnType<typeof userEvent.setup>) => user.keyboard("{Escape}")],
    ["the corner X", async (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getAllByRole("button", { name: "Close" }).find((b) => b.getAttribute("data-testid") !== "upload-close")!)],
    ["the footer Close", async (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByTestId("upload-close"))],
  ])("asks before closing while an upload runs (%s), with Keep uploading focused", async (_name, close) => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf")]);
    await user.click(submit());
    await close(user);
    const stop = await screen.findByTestId("upload-stop-dialog");
    expect(within(stop).getByText("Stop uploading?")).toBeInTheDocument();
    expect(stop).toHaveAttribute("role", "alertdialog");
    expect(stop).toHaveTextContent("2 files haven't finished. Files that already uploaded stay in the dataset.");
    expect(onOpenChange).not.toHaveBeenCalled();
    await waitFor(() => expect(within(stop).getByRole("button", { name: "Keep uploading" })).toHaveFocus());
  });

  it("asks before closing while an upload runs when the overlay is clicked", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    const overlay = document.querySelector<HTMLElement>('div.fixed.inset-0[data-state="open"]');
    expect(overlay).not.toBeNull();
    await user.click(overlay!);
    expect(await screen.findByTestId("upload-stop-dialog")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("does not close the question when its own backdrop is clicked", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    await user.keyboard("{Escape}");
    await screen.findByTestId("upload-stop-dialog");
    const overlays = document.querySelectorAll<HTMLElement>('div.fixed.inset-0[data-state="open"]');
    await user.click(overlays[overlays.length - 1]!);
    expect(screen.getByTestId("upload-stop-dialog")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("Keep uploading dismisses the question and the uploads carry on", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Keep uploading" }));
    await waitFor(() => expect(screen.queryByTestId("upload-stop-dialog")).toBeNull());
    expect(entryFor("a.pdf").aborted).toBe(false);
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("Stop uploads aborts the requests and closes", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf")]);
    await user.click(submit());
    await user.click(screen.getByTestId("upload-close"));
    await user.click(await screen.findByRole("button", { name: "Stop uploads" }));
    expect(pending.every((p) => p.aborted)).toBe(true);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("aborts what is in flight when the dialog goes away", async () => {
    const user = userEvent.setup();
    const view = renderDialog();
    dropFiles([makeFile("a.pdf")]);
    await user.click(submit());
    view.unmount();
    expect(entryFor("a.pdf").aborted).toBe(true);
  });
});

describe("focus management (UI-SPEC accessibility)", () => {
  it("moves focus to the next row's action after a row is removed, and to Choose files when none is left", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf")]);
    await user.click(screen.getByRole("button", { name: "Remove a.pdf" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove b.pdf" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Remove b.pdf" }));
    await waitFor(() => expect(screen.getByTestId("upload-choose")).toHaveFocus());
  });

  it("starts a fresh, empty dialog at every opening", () => {
    const view = renderDialog({ initialFiles: [makeFile("first.pdf")] });
    expect(screen.getAllByTestId("upload-row")).toHaveLength(1);
    const element = (open: boolean) => (
      <QueryClientProvider client={client}>
        <FileUploadDialog dataset={{ id: "kb1", name: "Reports", docNum: 3 }} limits={LIMITS} open={open} onOpenChange={onOpenChange} />
      </QueryClientProvider>
    );
    view.rerender(element(false));
    view.rerender(element(true));
    expect(screen.queryByTestId("upload-row")).toBeNull();
  });
});

describe("accessibility: one polite status region (checker flag 6)", () => {
  it("is a visually hidden, polite status region that starts empty", () => {
    renderDialog();
    expect(live()).toHaveAttribute("role", "status");
    expect(live()).toHaveAttribute("aria-live", "polite");
    expect(live().className).toContain("sr-only");
    expect(live()).toHaveTextContent("");
  });

  it("announces files added and files not added", () => {
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf"), makeFile("c.gif")]);
    expect(live()).toHaveTextContent("2 files added");
    expect(live()).toHaveTextContent("1 file wasn't added");
  });

  it("announces the extra files a limit left out", () => {
    renderDialog();
    dropFiles([makeFile("1.pdf"), makeFile("2.pdf"), makeFile("3.pdf"), makeFile("4.pdf"), makeFile("5.pdf")]);
    expect(live()).toHaveTextContent("3 files added");
    expect(live()).toHaveTextContent("2 files weren't added");
  });

  it("announces the start and the end of a batch, and never a percentage", async () => {
    const user = userEvent.setup();
    renderDialog();
    dropFiles([makeFile("a.pdf"), makeFile("b.pdf")]);
    await user.click(submit());
    expect(live()).toHaveTextContent("Uploading 2 files");
    await sendProgress("a.pdf", 50, 100);
    expect(live().textContent).not.toMatch(/%/);
    await succeed("a.pdf");
    await fail("b.pdf", 500, "boom");
    expect(live()).toHaveTextContent("1 uploaded, 1 failed");
    expect(live().textContent).not.toMatch(/%/);
  });
});

describe("source gates", () => {
  it("adds no markup injection and no drop library", async () => {
    const sources = import.meta.glob("./*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const production = Object.entries(sources).filter(([path]) => !path.endsWith(".test.tsx"));
    expect(production.length).toBeGreaterThan(2);
    for (const [path, source] of production) {
      expect({ path, injects: /dangerouslySetInnerHTML/.test(source) }).toEqual({ path, injects: false });
      expect({ path, library: /react-dropzone/.test(source) }).toEqual({ path, library: false });
    }
  });
});
