import { describe, expect, it } from "vitest";
import { createDatasetServer, DATASET_ID, datasetRow } from "./dataset-server";

const call = (server: ReturnType<typeof createDatasetServer>, method: string, url: string, data?: unknown) =>
  server.adapter({ method, url, data, headers: {} } as never) as Promise<{ data: { code: number; data: unknown } }>;

describe("test server area handlers (R-167)", () => {
  it("answers 404 when nothing matches", async () => {
    const server = createDatasetServer();
    await expect(call(server, "GET", "/nope")).rejects.toMatchObject({ response: { status: 404 } });
  });

  it("runs area handlers before core routes, in order, first answer wins", async () => {
    const server = createDatasetServer();
    server.use(({ method, url, ok }) => (url === "/x" ? ok({ from: "a", method }) : undefined));
    server.use(({ url, ok }) => (url === "/x" || url === "/api/v1/models" ? ok({ from: "b" }) : undefined));
    expect((await call(server, "GET", "/x")).data.data).toEqual({ from: "a", method: "GET" });
    expect((await call(server, "GET", "/api/v1/models")).data.data).toEqual({ from: "b" });
  });

  it("lets a forced failure win over an area", async () => {
    const server = createDatasetServer();
    server.use(({ ok }) => ok("area"));
    server.forced["GET /x"] = { status: 500, message: "boom" };
    await expect(call(server, "GET", "/x")).rejects.toMatchObject({ response: { status: 500 } });
  });

  it("keeps a held request held before an area answers", async () => {
    const server = createDatasetServer();
    server.use(({ ok }) => ok("area"));
    let release: () => void = () => {};
    server.holds["GET /x"] = new Promise<void>((r) => (release = r));
    let done = false;
    const p = call(server, "GET", "/x").then(() => (done = true));
    await Promise.resolve();
    expect(done).toBe(false);
    release();
    await p;
    expect(done).toBe(true);
  });

  it("passes params, parsed method and a POST body to handlers and supports failure()", async () => {
    const server = createDatasetServer();
    server.use(({ method, url, config, failure, ok }) => {
      if (url !== "/p") return undefined;
      if (method !== "POST") return failure({ status: 405, message: "no" });
      return ok(JSON.parse(String(config.data)));
    });
    expect((await call(server, "POST", "/p", JSON.stringify({ a: 1 }))).data.data).toEqual({ a: 1 });
    await expect(call(server, "GET", "/p")).rejects.toMatchObject({ response: { status: 405 } });
  });

  it("isolates area state per server and clears it on reset, keeping handlers", async () => {
    const a = createDatasetServer();
    const b = createDatasetServer();
    a.areaState("k", () => ({ n: 0 })).n = 5;
    expect(b.areaState("k", () => ({ n: 0 })).n).toBe(0);
    expect(a.areaState("k", () => ({ n: 0 })).n).toBe(5);
    a.use(({ ok }) => ok("still"));
    a.reset();
    expect(a.areaState("k", () => ({ n: 0 })).n).toBe(0);
    expect((await call(a, "GET", "/y")).data.data).toBe("still");
  });

  it("still serves core routes when no area answers", async () => {
    const server = createDatasetServer();
    server.datasets[DATASET_ID] = datasetRow();
    server.use(() => undefined);
    const res = await call(server, "GET", `/api/v1/datasets/${DATASET_ID}`);
    expect(res.data.code).toBe(0);
  });
});
