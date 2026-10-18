import type { AxiosProgressEvent } from "axios";
import type { AreaHandler, DatasetServer } from "../dataset-server";

/**
 * Test-server area for the document viewer (R-167): `GET .../documents/{doc}/content` as the file itself (a Blob typed
 * as the server would type it, with download progress) and with `?format=text` as `{text, cut}`. Content lives in
 * `server.areaState("content", ...)`, so a reset clears it. Fake data only.
 */

export interface StoredContent {
  /** The decoded start of a text-like file, for `?format=text`. */
  text?: string;
  cut?: boolean;
  /** The file for a download or an image: its content type and byte length. */
  type?: string;
  bytes?: number;
  /** When false the progress events carry no total (the size is unknown). */
  knownSize?: boolean;
}

export interface ContentState {
  byDoc: Record<string, StoredContent>;
  /** When set, a file download reports half its progress and then waits for this promise. */
  gate: Promise<void> | null;
}

export const contentStateOf = (server: DatasetServer): ContentState => server.areaState<ContentState>("content", () => ({ byDoc: {}, gate: null }));

export const contentUrl = (datasetId: string, docId: string): string => `/api/v1/datasets/${datasetId}/documents/${docId}/content`;

/** Stores the text a text-like file answers with. */
export function setTextContent(server: DatasetServer, docId: string, text: string, cut = false): void {
  const entry = (contentStateOf(server).byDoc[docId] ??= {});
  entry.text = text;
  entry.cut = cut;
}

/** Stores the file a download or an image request answers with. */
export function setFileContent(server: DatasetServer, docId: string, type: string, bytes = 1000, knownSize = true): void {
  const entry = (contentStateOf(server).byDoc[docId] ??= {});
  entry.type = type;
  entry.bytes = bytes;
  entry.knownSize = knownSize;
}

/** Holds the next file downloads halfway; the returned function lets them finish. */
export function holdDownloads(server: DatasetServer): () => void {
  let release: () => void = () => {};
  contentStateOf(server).gate = new Promise<void>((resolve) => (release = resolve));
  return release;
}

const CONTENT_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/documents\/([^/]+)\/content$/;

export const handle: AreaHandler = async ({ server, config, method, url, params, ok }) => {
  const matched = CONTENT_ROUTE.exec(url);
  if (!matched || method !== "GET") return undefined;
  const [, datasetId, docId] = matched as unknown as [string, string, string];
  if (server.datasets[datasetId] === undefined || !(server.documents[datasetId] ?? []).some((d) => d.id === docId)) return undefined;
  const state = contentStateOf(server);
  const entry = state.byDoc[docId] ?? {};
  if (params.format === "text") return ok({ text: entry.text ?? "", cut: entry.cut === true });

  const bytes = entry.bytes ?? 1000;
  const total = entry.knownSize === false ? undefined : bytes;
  const progress = (loaded: number): void => config.onDownloadProgress?.({ loaded, total, bytes: loaded } as AxiosProgressEvent);
  progress(Math.floor(bytes / 2));
  if (state.gate !== null) await state.gate;
  progress(bytes);
  const blob = new Blob([new Uint8Array(Math.min(bytes, 64))], { type: entry.type ?? "application/octet-stream" });
  return { data: blob, status: 200, statusText: "OK", headers: { "content-type": entry.type ?? "application/octet-stream" }, config };
};
