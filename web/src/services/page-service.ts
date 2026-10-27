import { documentContentPath, documentPageImagePath } from "@/constants/api-paths";
import { http, request } from "./http";
import { asRecord, count, text } from "./mapping";

/**
 * Page images, the original file and the text preview (plan 04-20). Binary calls go through `services/http.ts`, so the
 * Authorization header travels as a header and no token is ever put in a URL. This module makes no object URL: a component
 * does that, and only for the types `fetchPageImage` has already checked.
 */

/** Raised when the server answers a blob of a type the SPA will not display. */
export class PreviewTypeError extends Error {
  readonly contentType: string;
  constructor(contentType: string) {
    super("Unsupported preview type");
    this.name = "PreviewTypeError";
    this.contentType = contentType;
  }
}

export const PAGE_IMAGE_TIMEOUT_MS = 30000;
export const TEXT_PREVIEW_TIMEOUT_MS = 30000;
const IMAGE_TYPES = ["image/jpeg", "image/png"] as const;

/** True for the two image types a component may turn into an object URL. */
export function isDisplayableImage(type: string): boolean {
  return (IMAGE_TYPES as readonly string[]).includes(type);
}

/**
 * GET .../pages/{n}/image as a Blob. An error answer arrives as a Blob too, so a failure is classified by its HTTP status
 * only (the shared client leaves `code` at -1). A blob of any other type than JPEG or PNG is rejected.
 */
export async function fetchPageImage(datasetId: string, docId: string, page: number, signal?: AbortSignal): Promise<Blob> {
  const response = await http.request<Blob>({
    url: documentPageImagePath(datasetId, docId, page),
    method: "GET",
    responseType: "blob",
    timeout: PAGE_IMAGE_TIMEOUT_MS,
    signal,
    silent: true,
  });
  const blob = response.data;
  if (!(blob instanceof Blob) || !isDisplayableImage(blob.type)) throw new PreviewTypeError(blob instanceof Blob ? blob.type : "");
  return blob;
}

export interface TextPreview {
  text: string;
  /** True when the server cut the text at its preview limit. */
  cut: boolean;
}

/** GET .../content?format=text: the decoded start of a text-like file. Silent: the viewer renders its own error. */
export async function fetchTextPreview(datasetId: string, docId: string, signal?: AbortSignal): Promise<TextPreview> {
  const dto = asRecord(
    await request<unknown>({ url: documentContentPath(datasetId, docId), method: "GET", params: { format: "text" }, timeout: TEXT_PREVIEW_TIMEOUT_MS, signal }, { silent: true }),
  );
  return { text: text(dto.text), cut: dto.cut === true || count(dto.cut) === 1 };
}

export interface DownloadOptions {
  signal?: AbortSignal;
  onProgress?: (loaded: number, total: number | undefined) => void;
}

/**
 * GET .../content as a Blob for a download or an image file. `timeout: 0` because a large file on a slow link takes
 * minutes; the caller ends it through the signal. The Blob is returned as the server typed it: a component decides what to
 * do with it and never opens it inline unless it is `image/jpeg` or `image/png`.
 */
export async function downloadDocument(datasetId: string, docId: string, options: DownloadOptions = {}): Promise<Blob> {
  const response = await http.request<Blob>({
    url: documentContentPath(datasetId, docId),
    method: "GET",
    responseType: "blob",
    timeout: 0,
    signal: options.signal,
    onDownloadProgress: (event) => options.onProgress?.(event.loaded, event.total),
    silent: true,
  });
  return response.data;
}


/** Opaque figure id, authenticated header, and a bounded PNG response. */
export async function fetchDocumentAsset(id: string, signal?: AbortSignal): Promise<Blob> {
  const response = await http.request<Blob>({ url: `/api/v1/documents/images/${encodeURIComponent(id)}`, method: "GET", responseType: "blob", timeout: PAGE_IMAGE_TIMEOUT_MS, signal, silent: true });
  const blob = response.data;
  if (!(blob instanceof Blob) || blob.type !== "image/png" || blob.size > 8 * 1024 * 1024) throw new PreviewTypeError(blob instanceof Blob ? blob.type : "");
  return blob;
}
