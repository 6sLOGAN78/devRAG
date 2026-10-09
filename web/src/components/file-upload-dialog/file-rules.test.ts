import { describe, expect, it } from "vitest";
import {
  ALLOWED_EXTENSIONS,
  DEFAULT_LIMITS,
  applyBatchLimits,
  checkFile,
  fileKey,
  formatBytes,
  lastExtension,
  resolveUploadLimits,
} from "./file-rules";

const limits = { maxFileBytes: 1000, maxFilesPerRequest: 20, maxDocuments: 10000 };
const file = (name: string, size = 10, lastModified = 1) => new File([new Uint8Array(size)], name, { lastModified });
const reasonOf = (f: File, options?: { isDirectory?: boolean }) => {
  const result = checkFile(f, limits, ALLOWED_EXTENSIONS, options);
  return result.ok ? "ok" : result.reason;
};

describe("defaults (D-11, D-12, D-13, D-28)", () => {
  it("equal the server defaults", () => {
    expect(DEFAULT_LIMITS).toEqual({ maxFileBytes: 104857600, maxFilesPerRequest: 20, maxDocuments: 10000 });
    expect([...ALLOWED_EXTENSIONS]).toEqual(["pdf", "docx", "pptx", "xlsx", "txt", "md", "markdown", "csv", "json", "html", "htm", "epub", "jpg", "jpeg", "png", "mp3", "wav"]);
  });

  it("allow only jpg, jpeg and png among the images (D-28)", () => {
    for (const refused of ["gif", "bmp", "tiff", "tif", "webp", "svg", "exe"]) expect(ALLOWED_EXTENSIONS).not.toContain(refused);
  });
});

describe("lastExtension", () => {
  it("is the lower-cased text after the last dot, and empty when there is none", () => {
    expect(lastExtension("a.PDF")).toBe("pdf");
    expect(lastExtension("a.pdf.exe")).toBe("exe");
    expect(lastExtension("archive.tar.gz")).toBe("gz");
    expect(lastExtension("noext")).toBe("");
    expect(lastExtension("trailing.")).toBe("");
    expect(lastExtension("")).toBe("");
  });
});

describe("checkFile (UI-12 client checks, in order)", () => {
  it.each([
    ["a.PDF", "ok"],
    ["a.pdf.exe", "extension"],
    ["noext", "noExtension"],
    ["x.gif", "extension"],
    ["x.webp", "extension"],
    ["x.bmp", "extension"],
    ["x.tiff", "extension"],
    ["x.jpg", "ok"],
    ["x.jpeg", "ok"],
    ["x.png", "ok"],
    ["song.MP3", "ok"],
  ])("%s is %s", (name, expected) => {
    expect(reasonOf(file(name))).toBe(expected);
  });

  it("refuses a name over 255 characters and accepts exactly 255", () => {
    expect(reasonOf(file(`${"a".repeat(252)}.pdf`))).toBe("nameLong");
    expect(reasonOf(file(`${"a".repeat(251)}.pdf`))).toBe("ok");
  });

  it("refuses an empty file", () => {
    expect(reasonOf(file("a.pdf", 0))).toBe("empty");
  });

  it("accepts exactly the limit and refuses one byte more", () => {
    expect(reasonOf(file("a.pdf", 1000))).toBe("ok");
    expect(reasonOf(file("a.pdf", 1001))).toBe("size");
  });

  it("reports a directory entry as a folder", () => {
    expect(reasonOf(file("docs", 0), { isDirectory: true })).toBe("folder");
  });

  it("checks in the documented order: folder, name, extension, empty, size", () => {
    expect(reasonOf(file(`${"a".repeat(300)}.exe`, 0), { isDirectory: true })).toBe("folder");
    expect(reasonOf(file(`${"a".repeat(300)}.exe`, 0))).toBe("nameLong");
    expect(reasonOf(file("a.exe", 0))).toBe("extension");
    expect(reasonOf(file("a.pdf", 0))).toBe("empty");
  });

  it("uses the extension list it is given, normalising dots and case", () => {
    expect(checkFile(file("a.pdf"), limits, ["txt"])).toEqual({ ok: false, reason: "extension" });
    expect(checkFile(file("a.TXT"), limits, [".TXT"])).toEqual({ ok: true });
  });
});

describe("resolveUploadLimits (D-12: the server decides, with compiled-in fallbacks)", () => {
  it("falls back to the defaults when the dataset carries no limits", () => {
    expect(resolveUploadLimits(null)).toEqual({ ...DEFAULT_LIMITS, allowedExtensions: [...ALLOWED_EXTENSIONS] });
  });

  it("uses what the server reports", () => {
    expect(resolveUploadLimits({ maxFileBytes: 2048, maxFilesPerRequest: 5, maxDocuments: 50, allowedExtensions: ["pdf", ".TXT"] })).toEqual({
      maxFileBytes: 2048,
      maxFilesPerRequest: 5,
      maxDocuments: 50,
      allowedExtensions: ["pdf", "txt"],
    });
  });

  it("falls back per field when a value is zero or the list is empty", () => {
    expect(resolveUploadLimits({ maxFileBytes: 0, maxFilesPerRequest: 0, maxDocuments: 0, allowedExtensions: [] })).toEqual({ ...DEFAULT_LIMITS, allowedExtensions: [...ALLOWED_EXTENSIONS] });
  });
});

describe("applyBatchLimits (D-13)", () => {
  const many = (n: number) => Array.from({ length: n }, (_, i) => file(`f${i}.pdf`, 10, i + 1));

  it("keeps the first maxFiles and reports the extra count", () => {
    const result = applyBatchLimits(many(25), new Set(), { maxFiles: 20, remaining: 1000 });
    expect(result.accepted.map((f) => f.name)).toEqual(many(20).map((f) => f.name));
    expect(result).toMatchObject({ tooMany: 5, datasetFull: 0, duplicates: 0 });
  });

  it("keeps files up to the dataset's remaining room and reports the extra count", () => {
    const result = applyBatchLimits(many(5), new Set(), { maxFiles: 20, remaining: 3 });
    expect(result.accepted).toHaveLength(3);
    expect(result).toMatchObject({ tooMany: 0, datasetFull: 2 });
  });

  it("applies the request limit first and the dataset room to what is left", () => {
    const result = applyBatchLimits(many(10), new Set(), { maxFiles: 6, remaining: 4 });
    expect(result.accepted).toHaveLength(4);
    expect(result).toMatchObject({ tooMany: 4, datasetFull: 2 });
  });

  it("ignores a file with the same name, size and modified time as one already queued, and repeats inside the batch", () => {
    const first = file("a.pdf", 10, 5);
    const queued = new Set([fileKey(first)]);
    const result = applyBatchLimits([file("a.pdf", 10, 5), file("a.pdf", 11, 5), file("b.pdf", 10, 5), file("b.pdf", 10, 5)], queued, { maxFiles: 20, remaining: 100 });
    expect(result.accepted.map((f) => `${f.name}:${f.size}`)).toEqual(["a.pdf:11", "b.pdf:10"]);
    expect(result.duplicates).toBe(2);
  });

  it("never lets a negative room through", () => {
    const result = applyBatchLimits(many(2), new Set(), { maxFiles: -1, remaining: -3 });
    expect(result.accepted).toEqual([]);
  });
});

describe("formatBytes (base 1024, one decimal below 10)", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1536, "1.5 KB"],
    [104857600, "100 MB"],
    [9.5 * 1024 * 1024, "9.5 MB"],
    [12 * 1024 * 1024, "12 MB"],
    [1073741824, "1 GB"],
  ])("%s is %s", (bytes, expected) => {
    expect(formatBytes(bytes, "en")).toBe(expected);
  });

  it("follows the language's number format", () => {
    expect(formatBytes(1536, "de")).toBe("1,5 KB");
  });
});
