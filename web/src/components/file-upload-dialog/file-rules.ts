import type { UploadLimitsView } from "@/services/dataset-service";

/**
 * Client-side upload rules (UI-12, D-11, D-12, D-13, D-28). They save the user a wasted upload; the server stays
 * authoritative and repeats every check. Plain TypeScript, no React, so each rule is unit-tested on its own.
 */

/** The server's default extension list (D-12). Images are jpg, jpeg and png only (D-28). */
export const ALLOWED_EXTENSIONS: readonly string[] = ["pdf", "docx", "pptx", "xlsx", "txt", "md", "markdown", "csv", "json", "html", "htm", "epub", "jpg", "jpeg", "png", "mp3", "wav"];

export interface UploadLimits {
  /** Bytes per file. */
  maxFileBytes: number;
  /** Files per upload batch. */
  maxFilesPerRequest: number;
  /** Documents one dataset may hold. */
  maxDocuments: number;
}

/** The server defaults, used when the dataset detail carries no `upload_limits`. */
export const DEFAULT_LIMITS: UploadLimits = { maxFileBytes: 104857600, maxFilesPerRequest: 20, maxDocuments: 10000 };

export interface ResolvedLimits extends UploadLimits {
  allowedExtensions: string[];
}

const MAX_NAME_LENGTH = 255;

/** Lower-cased, without a leading dot. */
const normalizeExtension = (ext: string): string => ext.trim().replace(/^\./, "").toLowerCase();

const positive = (value: number | undefined, fallback: number): number => (typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback);

/** The limits the dialog applies: what the server reported, with the compiled-in default for each missing or invalid part. */
export function resolveUploadLimits(view: UploadLimitsView | null): ResolvedLimits {
  const extensions = (view?.allowedExtensions ?? []).map(normalizeExtension).filter((ext) => ext !== "");
  return {
    maxFileBytes: positive(view?.maxFileBytes, DEFAULT_LIMITS.maxFileBytes),
    maxFilesPerRequest: positive(view?.maxFilesPerRequest, DEFAULT_LIMITS.maxFilesPerRequest),
    maxDocuments: positive(view?.maxDocuments, DEFAULT_LIMITS.maxDocuments),
    allowedExtensions: extensions.length > 0 ? extensions : [...ALLOWED_EXTENSIONS],
  };
}

/** The text after the last dot, lower-cased; empty when the name has no dot or ends with one. Only this one decides (`a.pdf.exe` is `exe`). */
export function lastExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

export type RejectReason = "folder" | "nameLong" | "extension" | "noExtension" | "empty" | "size";

export type FileCheck = { ok: true } | { ok: false; reason: RejectReason };

export interface CheckOptions {
  /** The drop handler's verdict that this entry is a folder. */
  isDirectory?: boolean;
}

/** Checks one file, in the documented order: folder, name length, extension, empty, size. The first failure wins. */
export function checkFile(file: { name: string; size: number }, limits: Pick<UploadLimits, "maxFileBytes">, extensions: readonly string[], options: CheckOptions = {}): FileCheck {
  if (options.isDirectory === true) return { ok: false, reason: "folder" };
  if (Array.from(file.name).length > MAX_NAME_LENGTH) return { ok: false, reason: "nameLong" };
  const ext = lastExtension(file.name);
  if (ext === "") return { ok: false, reason: "noExtension" };
  if (!extensions.map(normalizeExtension).includes(ext)) return { ok: false, reason: "extension" };
  if (file.size === 0) return { ok: false, reason: "empty" };
  if (file.size > limits.maxFileBytes) return { ok: false, reason: "size" };
  return { ok: true };
}

/** Identity of a picked file: the same name, size and modified time is the same file. */
export function fileKey(file: { name: string; size: number; lastModified: number }): string {
  return `${file.name}\u0000${file.size}\u0000${file.lastModified}`;
}

export interface BatchRoom {
  /** Files one batch may hold. */
  maxFiles: number;
  /** Documents the dataset can still take. */
  remaining: number;
}

export interface BatchResult<T> {
  accepted: T[];
  /** Files left out because the same file was already queued (or repeated in this drop). */
  duplicates: number;
  /** Files left out by the per-batch limit. */
  tooMany: number;
  /** Files left out because the dataset would exceed its document limit. */
  datasetFull: number;
}

/**
 * Applies the batch limits (D-13) to files that already passed the per-file checks: repeats are dropped first, then the
 * first `maxFiles` are kept, then as many as the dataset has room for. The counts feed one notice above the list.
 */
export function applyBatchLimits<T extends { name: string; size: number; lastModified: number }>(files: readonly T[], queuedKeys: ReadonlySet<string>, room: BatchRoom): BatchResult<T> {
  const seen = new Set(queuedKeys);
  const fresh: T[] = [];
  for (const file of files) {
    const key = fileKey(file);
    if (seen.has(key)) continue;
    seen.add(key);
    fresh.push(file);
  }
  const maxFiles = Math.max(0, Math.floor(room.maxFiles));
  const withinBatch = fresh.slice(0, maxFiles);
  const remaining = Math.max(0, Math.floor(room.remaining));
  const accepted = withinBatch.slice(0, remaining);
  return {
    accepted,
    duplicates: files.length - fresh.length,
    tooMany: fresh.length - withinBatch.length,
    datasetFull: withinBatch.length - accepted.length,
  };
}

const UNITS = ["B", "KB", "MB", "GB"] as const;

/** "1.5 KB", "100 MB": base 1024, one decimal below 10, numbers in the active language. */
export function formatBytes(bytes: number, language: string): string {
  let value = Number.isFinite(bytes) && bytes > 0 ? bytes : 0;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit > 0 && value < 10 ? 1 : 0;
  let formatted: string;
  try {
    formatted = new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value);
  } catch {
    formatted = value.toFixed(digits);
  }
  return `${formatted} ${UNITS[unit]}`;
}
