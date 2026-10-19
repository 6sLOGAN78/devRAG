/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import pkg from "../../package.json";

/**
 * Phase 4 source gate (plan 04-35): the production bundle carries no raw HTML injection, no iframe, none of the
 * packages Phase 4 decided against (D-21, D-24), and no fixture from the test-server tree (T-04-23-03).
 */
const all = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const production = Object.entries(all).filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes("/src/test/"));

const FORBIDDEN_TEXT = [
  "dangerouslySetInnerHTML",
  "iframe",
  "react-pdf-highlighter",
  "pdfjs-dist",
  "@tanstack/react-table",
  "@radix-ui/react-switch",
  "@radix-ui/react-checkbox",
  "@radix-ui/react-tabs",
];
const FORBIDDEN_PACKAGES = FORBIDDEN_TEXT.filter((name) => name.includes("/") || name.includes("-")).filter((name) => name !== "iframe");
const TEST_TREE_IMPORT = /(?:from|import)\s*\(?\s*["'](?:@\/test(?:\/|["'])|src\/test|\.\/test\/|\.\.\/test\/)/;

function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

export function importsTestTree(source: string): boolean {
  return TEST_TREE_IMPORT.test(code(source));
}

describe("phase 4 source gate", () => {
  it("is not vacuous", () => {
    expect(production.length).toBeGreaterThan(50);
    expect(Object.keys(all).some((path) => path.includes("/src/test/"))).toBe(true);
  });

  it.each(FORBIDDEN_TEXT)("no production file mentions %s", (needle) => {
    const hits = production.filter(([, source]) => code(source).includes(needle)).map(([path]) => path);
    expect(hits).toEqual([]);
  });

  it("no production file imports from the test-server tree", () => {
    const hits = production.filter(([, source]) => importsTestTree(source)).map(([path]) => path);
    expect(hits).toEqual([]);
  });

  it("the import check recognises each forbidden form", () => {
    expect(importsTestTree(`import { x } from "@/test/dataset-server";`)).toBe(true);
    expect(importsTestTree(`import { x } from "src/test/mail";`)).toBe(true);
    expect(importsTestTree(`import { x } from "./test/a";`)).toBe(true);
    expect(importsTestTree(`import { x } from "../test/a";`)).toBe(true);
    expect(importsTestTree(`const m = await import("@/test/live/x");`)).toBe(true);
    expect(importsTestTree(`import { x } from "@/testing-library";`)).toBe(false);
  });

  it("none of the rejected packages is a dependency", () => {
    const declared = { ...(pkg as { dependencies?: object }).dependencies, ...(pkg as { devDependencies?: object }).devDependencies };
    for (const name of FORBIDDEN_PACKAGES) expect(Object.keys(declared), name).not.toContain(name);
  });
});
