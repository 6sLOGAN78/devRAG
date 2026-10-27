import { describe, expect, it } from "vitest";
import { CHUNK_ROUTE, chunkPath, DATASET_LOGS_ROUTE, datasetLogsPath, DOCUMENT_VIEWER_ROUTE, documentViewerPath } from "./app-paths";
import { CHATS_ROUTE, DATASET_TESTING_ROUTE, chatPath, retrievalTestPath } from "./app-paths";

describe("Phase 4 path builders", () => {
  it("build each link from its route constant and encode the ids", () => {
    expect(datasetLogsPath("a b")).toBe(`${DATASET_LOGS_ROUTE}?id=a%20b`);
    expect(chunkPath("k/1", "d&2")).toBe(`${CHUNK_ROUTE}?id=k%2F1&doc=d%262`);
    expect(documentViewerPath("k1", "d1")).toBe(`${DOCUMENT_VIEWER_ROUTE}?id=k1&doc=d1`);
    expect([DATASET_LOGS_ROUTE, CHUNK_ROUTE, DOCUMENT_VIEWER_ROUTE]).toEqual(["/dataset/logs", "/chunk", "/document"]);
  });
});

describe("Phase 5 path builders", () => {
  it("encodes assistant and session ids in chat links", () => {
    expect(chatPath("a/b", "s&1")).toBe(`${CHATS_ROUTE}?chat=a%2Fb&session=s%261`);
    expect(chatPath("a")).toBe("/chats?chat=a");
    expect(retrievalTestPath("d 1")).toBe(`${DATASET_TESTING_ROUTE}?id=d%201`);
  });
  it("adds only positive whole page numbers to document links", () => {
    expect(documentViewerPath("d", "doc", 2)).toBe("/document?id=d&doc=doc&page=2");
    for (const page of [0, -1, 1.2, Infinity, NaN]) expect(documentViewerPath("d", "doc", page)).toBe("/document?id=d&doc=doc");
  });
});
