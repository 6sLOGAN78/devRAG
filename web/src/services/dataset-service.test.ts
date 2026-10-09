import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createDataset, getDataset, listDatasets } from "./dataset-service";
import { http } from "./http";

const originalAdapter = http.defaults.adapter;
let body: unknown;
let seen: InternalAxiosRequestConfig[] = [];

const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  return Promise.resolve({ data: body, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;
};

beforeEach(() => {
  seen = [];
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

const success = (data: unknown) => ({ code: 0, message: "", data });

const TENANT = "0123456789abcdef0123456789abcdef";

const datasetDto = {
  id: "kb1",
  name: "Reports",
  description: "Quarterly reports",
  avatar: "",
  language: "English",
  permission: "team",
  embd_id: "embed-one@OpenRouter",
  embedding_dimension: 1024,
  parser_id: "naive",
  parser_config: { chunk_token_num: 512 },
  doc_num: 3,
  chunk_num: 40,
  token_num: 9000,
  tenant_id: TENANT,
  created_by: "u1",
  create_time: 1700000000000,
  update_time: 1700000100000,
};

const params = () => seen[0]?.params as Record<string, unknown>;

describe("listDatasets (KB-02, TEN-13)", () => {
  it("sends tenant_id, page, page_size and keywords, stays silent and maps an explicit field list", async () => {
    body = success({ items: [{ ...datasetDto, secret_thing: "never", status: "1" }], total: 1 });
    const result = await listDatasets({ tenantId: TENANT, page: 2, pageSize: 12, keywords: "rep" });
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe("/api/v1/datasets");
    expect(seen[0]?.method).toBe("get");
    expect(params()).toEqual({ tenant_id: TENANT, page: 2, page_size: 12, keywords: "rep" });
    expect(seen[0]?.silent).toBe(true);
    expect(result.total).toBe(1);
    expect(result.items).toEqual([
      {
        id: "kb1",
        name: "Reports",
        description: "Quarterly reports",
        permission: "team",
        embdId: "embed-one@OpenRouter",
        embeddingDimension: 1024,
        docNum: 3,
        createdBy: "u1",
        tenantId: TENANT,
        updateTime: 1700000100000,
      },
    ]);
    expect(JSON.stringify(result)).not.toContain("secret_thing");
  });

  it("clamps page to at least 1 before the request (T-03-23-03)", async () => {
    body = success({ items: [], total: 0 });
    for (const page of [0, -4, Number.NaN]) {
      seen = [];
      await listDatasets({ tenantId: TENANT, page, pageSize: 12, keywords: "" });
      expect(params().page).toBe(1);
    }
    seen = [];
    await listDatasets({ tenantId: TENANT, page: 3.9, pageSize: 12, keywords: "" });
    expect(params().page).toBe(3);
  });

  it("clamps page_size to 1..100", async () => {
    body = success({ items: [], total: 0 });
    await listDatasets({ tenantId: TENANT, page: 1, pageSize: 500, keywords: "" });
    expect(params().page_size).toBe(100);
    seen = [];
    await listDatasets({ tenantId: TENANT, page: 1, pageSize: 0, keywords: "" });
    expect(params().page_size).toBe(1);
    seen = [];
    await listDatasets({ tenantId: TENANT, page: 1, pageSize: -3, keywords: "" });
    expect(params().page_size).toBe(1);
  });

  it("cuts keywords to 128 characters and omits an empty search", async () => {
    body = success({ items: [], total: 0 });
    await listDatasets({ tenantId: TENANT, page: 1, pageSize: 12, keywords: "x".repeat(300) });
    expect(params().keywords).toBe("x".repeat(128));
    seen = [];
    await listDatasets({ tenantId: TENANT, page: 1, pageSize: 12, keywords: "" });
    expect(params()).not.toHaveProperty("keywords");
  });

  it("coerces strings, numbers and missing values, and gives an empty page for a bad body", async () => {
    body = success({
      items: [{ id: 7, name: null, description: undefined, permission: 3, embd_id: null, embedding_dimension: "x", doc_num: "4", created_by: 1, tenant_id: null, update_time: "9" }, "junk", null],
      total: "2",
    });
    const result = await listDatasets({ tenantId: TENANT, page: 1, pageSize: 12, keywords: "" });
    expect(result.total).toBe(2);
    expect(result.items[0]).toEqual({
      id: "7",
      name: "",
      description: "",
      permission: "",
      embdId: "",
      embeddingDimension: null,
      docNum: 4,
      createdBy: "1",
      tenantId: "",
      updateTime: 9,
    });
    expect(result.items).toHaveLength(3);
    body = success("nope");
    await expect(listDatasets({ tenantId: TENANT, page: 1, pageSize: 12, keywords: "" })).resolves.toEqual({ items: [], total: 0 });
  });
});

describe("getDataset (KB-02)", () => {
  it("maps the detail with upload_limits to uploadLimits", async () => {
    body = success({
      ...datasetDto,
      upload_limits: { max_file_bytes: 104857600, max_files_per_request: 20, max_documents: 1000, allowed_extensions: ["pdf", "docx", 5], extra: "x" },
    });
    const detail = await getDataset("kb1");
    expect(seen[0]?.url).toBe("/api/v1/datasets/kb1");
    expect(seen[0]?.silent).toBe(true);
    expect(detail).toMatchObject({ id: "kb1", name: "Reports", language: "English", parserId: "naive", chunkNum: 40, tokenNum: 9000, createTime: 1700000000000 });
    expect(detail.uploadLimits).toEqual({ maxFileBytes: 104857600, maxFilesPerRequest: 20, maxDocuments: 1000, allowedExtensions: ["pdf", "docx"] });
  });

  it("gives null limits when the server sends none and encodes the id", async () => {
    body = success(datasetDto);
    const detail = await getDataset("a/b c");
    expect(detail.uploadLimits).toBeNull();
    expect(seen[0]?.url).toBe("/api/v1/datasets/a%2Fb%20c");
  });
});

describe("createDataset (KB-01, KB-04, D-26)", () => {
  it("POSTs the workspace and the fields with a 30 s timeout, silently, and maps the answer", async () => {
    body = success(datasetDto);
    const created = await createDataset({ tenantId: TENANT, name: "Reports", description: "Quarterly reports", embdId: "embed-one@OpenRouter", permission: "team" });
    expect(seen[0]?.url).toBe("/api/v1/datasets");
    expect(seen[0]?.method).toBe("post");
    expect(JSON.parse(String(seen[0]?.data))).toEqual({
      tenant_id: TENANT,
      name: "Reports",
      description: "Quarterly reports",
      embd_id: "embed-one@OpenRouter",
      permission: "team",
    });
    expect(seen[0]?.timeout).toBe(30000);
    expect(seen[0]?.silent).toBe(true);
    expect(created).toMatchObject({ id: "kb1", name: "Reports", permission: "team", embdId: "embed-one@OpenRouter" });
  });

  it("leaves out the optional fields the caller did not choose", async () => {
    body = success(datasetDto);
    await createDataset({ tenantId: TENANT, name: "Only a name" });
    expect(JSON.parse(String(seen[0]?.data))).toEqual({ tenant_id: TENANT, name: "Only a name" });
  });
});
