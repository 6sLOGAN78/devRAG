/**
 * A loopback stand-in for a third-party model provider, for the browser-tier live tests (plan 03-26, T-03-22-04).
 *
 * It is the other end of the wire, not a stub of devRag: the dockerised app really calls it when a provider is saved
 * (the connection test of each model) and the SPA's own services talk to the real app. It serves OpenAI-shaped chat and
 * embedding answers with made-up vectors, so the real provider key never has to enter a browser tier. It listens on
 * every interface (the app container reaches the host as `host.docker.internal`, dev compose only), on an ephemeral
 * port, for the lifetime of the test, and records nothing but the paths it was asked for.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { setTimeout as pause } from "node:timers/promises";

/** How the dev app container reaches the machine running the tests (extra_hosts in docker-compose.dev.yml). */
const STACK_HOST = "host.docker.internal";
export const FAKE_EMBEDDING_DIMENSION = 8;
const CHAT_TEXT = "Hello from the fake";

export interface FakeProvider {
  /** The base URL to hand to the app: `http://host.docker.internal:{port}/v1`. */
  stackBaseUrl: string;
  /** Paths requested so far, in order. */
  paths: string[];
  /** Embedding answers wait this many milliseconds (plan 04-34: keeps a parse running long enough to be cancelled). */
  delayMs: number;
  /** `refuse` answers every embedding call with a 400, the way a provider rejects an input (plan 04-34). */
  mode: "ok" | "refuse";
  chatMode: "plain" | "gated" | "marker";
  chatRequests: Record<string, unknown>[];
  releaseChat: () => void;
  close: () => Promise<void>;
}

function readBody(request: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      try {
        const parsed: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
        resolve(typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {});
      } catch {
        resolve({});
      }
    });
    request.on("error", () => resolve({}));
  });
}

function send(response: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  response.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) });
  response.end(payload);
}

function inputs(body: Record<string, unknown>): string[] {
  const value = body.input;
  if (typeof value === "string") return [value];
  return Array.isArray(value) ? value.map(String) : [];
}

export async function startFakeProvider(): Promise<FakeProvider> {
  const paths: string[] = [];
  const state = { delayMs: 0, mode: "ok" as "ok" | "refuse", chatMode: "plain" as "plain" | "gated" | "marker" };
  const chatRequests: Record<string, unknown>[] = [];
  const gates = new Set<() => void>();
  const releaseChat = () => { for (const release of gates) release(); gates.clear(); };
  const server: Server = createServer((request, response) => {
    void (async () => {
      const path = (request.url ?? "").split("?")[0];
      paths.push(path);
      const body = await readBody(request);
      const model = typeof body.model === "string" ? body.model : "";
      if (request.method === "GET" && path === "/health") return send(response, 200, { ok: true });
      if (request.method === "POST" && path === "/v1/embeddings") {
        if (state.delayMs > 0) await pause(state.delayMs);
        if (state.mode === "refuse") return send(response, 400, { error: { message: "input rejected by the fake", type: "invalid_request_error" } });
        const texts = inputs(body);
        const data = texts.map((_, index) => ({
          object: "embedding",
          index,
          embedding: Array.from({ length: FAKE_EMBEDDING_DIMENSION }, (__, j) => Math.round(((index + 1) / 10 + j / 100) * 10000) / 10000),
        }));
        const tokens = texts.reduce((sum, text) => sum + (text.split(/\s+/).filter(Boolean).length || 1), 0);
        return send(response, 200, { object: "list", data, model, usage: { prompt_tokens: tokens, total_tokens: tokens } });
      }
      if (request.method === "POST" && path === "/v1/chat/completions") {
        chatRequests.push(body);
        const content = state.chatMode === "marker" ? "Answer ##0$$ done." : CHAT_TEXT;
        if (body.stream === true) {
          response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
          const piece = (text: string, finish: string | null = null) => response.write(`data: ${JSON.stringify({ id: "chatcmpl-fake", object: "chat.completion.chunk", created: 1, model, choices: [{ index: 0, delta: { content: text }, finish_reason: finish }] })}\n\n`);
          piece(content.slice(0, 6));
          if (state.chatMode === "gated") {
            await new Promise<void>((resolve) => {
              const release = () => { gates.delete(release); response.off("close", release); resolve(); };
              gates.add(release);
              response.once("close", release);
            });
          }
          if (response.destroyed) return;
          piece(content.slice(6));
          piece("", "stop");
          response.end("data: [DONE]\n\n");
          return;
        }
        return send(response, 200, {
          id: "chatcmpl-fake",
          object: "chat.completion",
          created: 1,
          model,
          choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
          usage: { prompt_tokens: 11, completion_tokens: 5, total_tokens: 16 },
        });
      }
      return send(response, 404, { error: { message: "not found", type: "invalid_request_error" } });
    })();
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "0.0.0.0", () => resolve());
  });
  const port = (server.address() as AddressInfo).port;
  return {
    stackBaseUrl: `http://${STACK_HOST}:${port}/v1`,
    paths,
    chatRequests,
    releaseChat,
    get chatMode() { return state.chatMode; },
    set chatMode(value) { state.chatMode = value; },
    get delayMs() {
      return state.delayMs;
    },
    set delayMs(value: number) {
      state.delayMs = value;
    },
    get mode() {
      return state.mode;
    },
    set mode(value: "ok" | "refuse") {
      state.mode = value;
    },
    close: () =>
      new Promise<void>((resolve) => {
        releaseChat();
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}
