import { createParser } from "eventsource-parser";
import { getAuthorization } from "@/utils/authorization";
import { ApiError, isSameOrigin, parseRetryAfter, purgeSession } from "./http";
import { asRecord, text } from "./mapping";

export interface StreamOptions {
  url: string;
  body: unknown;
  signal?: AbortSignal;
  idleMs?: number;
  maxBufferBytes?: number;
  onFrame: (frame: unknown) => void;
}
const networkError = () => new ApiError({ code: -1, status: 0, kind: "network", message: "The answer stream was interrupted." });

/** Authenticated same-origin POST stream; the caller's controller owns stop and unmount. */
export async function postEventStream({ url, body, signal, idleMs = 60000, maxBufferBytes = 1048576, onFrame }: StreamOptions): Promise<"done" | "aborted"> {
  if (!isSameOrigin(url, undefined)) throw networkError();
  if (signal?.aborted) return "aborted";
  if (!Number.isFinite(idleMs) || idleMs <= 0 || !Number.isSafeInteger(maxBufferBytes) || maxBufferBytes < 1) throw networkError();
  const token = getAuthorization();
  const controller = new AbortController();
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout>;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let done = false;
  let buffered = 0, lineBytes = 0, afterCR = false;
  const aborted = new Promise<never>((_, reject) => controller.signal.addEventListener("abort", () => reject(new DOMException("Stream aborted", "AbortError")), { once: true }));
  // Attach the rejection handler before fetch, including a fetch implementation that ignores its signal.
  void aborted.catch(() => undefined);
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop, { once: true });
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(() => { timedOut = true; controller.abort(); }, idleMs);
  };
  const parser = createParser({
    maxBufferSize: maxBufferBytes,
    onError(error) { if (error.type === "max-buffer-size-exceeded") throw networkError(); },
    onEvent(event) {
      if (done) return;
      if (event.data === "[DONE]") { done = true; return; }
      let frame: unknown;
      try { frame = JSON.parse(event.data); } catch { return; }
      onFrame(frame);
    },
  });
  try {
    arm();
    const response = await Promise.race([fetch(url, {
      method: "POST", credentials: "same-origin", redirect: "error", signal: controller.signal,
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    }), aborted]);
    if (!response.ok) {
      const envelope = asRecord(await Promise.race([response.json().catch(() => null), aborted]));
      // Purging may unmount/abort the caller. Preserve the typed refusal after reading its body.
      if (response.status === 401 && token && token === getAuthorization()) purgeSession();
      throw new ApiError({ code: typeof envelope.code === "number" ? envelope.code : -1, status: response.status,
        message: text(envelope.message).slice(0, 160), data: envelope.data,
        requestId: response.headers.get("x-request-id") ?? undefined,
        retryAfter: parseRetryAfter(response.headers.get("retry-after") ?? undefined) });
    }
    if (response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "text/event-stream" || !response.body) throw networkError();
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (!done) {
      const piece = await Promise.race([reader.read(), aborted]);
      if (piece.done) throw networkError();
      if (piece.value.byteLength === 0) continue;
      arm();
      // Bound raw bytes per incomplete event/line, including invalid huge lines the parser discards.
      // A split CRLF is one newline. A blank line releases the event's byte budget.
      for (const byte of piece.value) {
        if (afterCR && byte === 10) { afterCR = false; continue; }
        afterCR = byte === 13;
        if (byte === 10 || byte === 13) {
          if (lineBytes === 0) buffered = 0;
          lineBytes = 0;
        } else lineBytes += 1;
        if (++buffered > maxBufferBytes) throw networkError();
      }
      parser.feed(decoder.decode(piece.value, { stream: true }));
    }
    return "done";
  } catch (error) {
    if (timedOut) throw new ApiError({ code: -1, status: 0, kind: "timeout", message: "The answer stream timed out." });
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) return "aborted";
    throw networkError();
  } finally {
    clearTimeout(timer!);
    signal?.removeEventListener("abort", stop);
    // Cancel before aborting fetch so the server can settle a partial turn promptly.
    if (reader) { void reader.cancel().catch(() => undefined); reader.releaseLock(); }
    controller.abort();
  }
}
