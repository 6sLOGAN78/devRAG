import { describe, expect, it } from "vitest";
import { CHUNK_ROUTE, chunkPath, DATASET_LOGS_ROUTE, datasetLogsPath, DOCUMENT_VIEWER_ROUTE, documentViewerPath } from "./app-paths";

describe("Phase 4 path builders", () => {
  it("build each link from its route constant and encode the ids", () => {
    expect(datasetLogsPath("a b")).toBe(`${DATASET_LOGS_ROUTE}?id=a%20b`);
    expect(chunkPath("k/1", "d&2")).toBe(`${CHUNK_ROUTE}?id=k%2F1&doc=d%262`);
    expect(documentViewerPath("k1", "d1")).toBe(`${DOCUMENT_VIEWER_ROUTE}?id=k1&doc=d1`);
    expect([DATASET_LOGS_ROUTE, CHUNK_ROUTE, DOCUMENT_VIEWER_ROUTE]).toEqual(["/dataset/logs", "/chunk", "/document"]);
  });
});
