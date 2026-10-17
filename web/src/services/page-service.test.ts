import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { downloadDocument, fetchPageImage, fetchTextPreview, PreviewTypeError } from "./page-service";
import { ApiError, http } from "./http";

const originalAdapter = http.defaults.adapter;
let reply: { status: number; data: unknown } = { status: 200, data: null };
let seen: InternalAxiosRequestConfig[] = [];
const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  if (reply.status >= 400) {
    return Promise.reject(Object.assign(new Error("failed"), { isAxiosError: true, config, response: { status: reply.status, data: reply.data, headers: new AxiosHeaders(), config } }));
  }
  config.onDownloadProgress?.({ loaded: 5, total: 10 } as never);
  return Promise.resolve({ data: reply.data, status: reply.status, statusText: "OK", headers: new AxiosHeaders(), config }) as never;
};
beforeEach(() => {
  seen = [];
  reply = { status: 200, data: null };
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});
const D = "0123456789abcdef0123456789abcdef";

describe("fetchPageImage (UI-17)", () => {
  it("requests a blob with a 30 s timeout, silently, through the shared client and returns a JPEG or PNG", async () => {
    reply = { status: 200, data: new Blob(["x"], { type: "image/jpeg" }) };
    const blob = await fetchPageImage(D, "d1", 3);
    expect(blob.type).toBe("image/jpeg");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/documents/d1/pages/3/image`);
    expect(seen[0]?.responseType).toBe("blob");
    expect(seen[0]?.timeout).toBe(30000);
    expect(seen[0]?.silent).toBe(true);
    expect(seen[0]?.url).not.toMatch(/token|authorization/i);
    reply = { status: 200, data: new Blob(["x"], { type: "image/png" }) };
    expect((await fetchPageImage(D, "d1", 1)).type).toBe("image/png");
  });

  it("rejects any other type with a PreviewTypeError", async () => {
    for (const type of ["image/svg+xml", "text/html", ""]) {
      reply = { status: 200, data: new Blob(["<svg/>"], { type }) };
      await expect(fetchPageImage(D, "d1", 1)).rejects.toBeInstanceOf(PreviewTypeError);
    }
  });

  it("classifies an error answer by status only (the body is a Blob)", async () => {
    reply = { status: 404, data: new Blob(['{"code":404}'], { type: "application/json" }) };
    const failure = await fetchPageImage(D, "d1", 99).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(404);
    expect((failure as ApiError).code).toBe(-1);
  });
});

describe("fetchTextPreview and downloadDocument (UI-17)", () => {
  it("asks for format=text and returns text and cut", async () => {
    reply = { status: 200, data: { code: 0, message: "", data: { text: "hi", cut: true, extra: 1 } } };
    expect(await fetchTextPreview(D, "d1")).toEqual({ text: "hi", cut: true });
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/documents/d1/content`);
    expect(seen[0]?.params).toEqual({ format: "text" });
    expect(seen[0]?.silent).toBe(true);
  });

  it("downloads as a blob with no timeout, the caller's signal and progress", async () => {
    reply = { status: 200, data: new Blob(["abc"], { type: "application/pdf" }) };
    const controller = new AbortController();
    const reports: Array<[number, number | undefined]> = [];
    const blob = await downloadDocument(D, "d1", { signal: controller.signal, onProgress: (loaded, total) => reports.push([loaded, total]) });
    expect(blob.type).toBe("application/pdf");
    expect(seen[0]?.timeout).toBe(0);
    expect(seen[0]?.signal).toBe(controller.signal);
    expect(seen[0]?.responseType).toBe("blob");
    expect(seen[0]?.silent).toBe(true);
    expect(reports).toEqual([[5, 10]]);
  });
});
