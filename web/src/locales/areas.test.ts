import { describe, expect, it } from "vitest";
import baseEn from "@/locales/en.json";
import baseZh from "@/locales/zh.json";
import { AREAS, en, mergeTrees, zh, type Tree } from "@/locales";
import { diffLocales, flatten } from "./locales.test";

describe("mergeTrees (R-167)", () => {
  it("returns the base unchanged when there is no part", () => {
    expect(mergeTrees({ a: { b: "x" } }, [])).toEqual({ a: { b: "x" } });
  });
  it("deep-merges parts without mutating sources", () => {
    const base: Tree = { a: { b: "x" } };
    const part: Tree = { a: { c: "y" }, d: "z" };
    const merged = mergeTrees(base, [{ label: "p.json", tree: part }]);
    expect(merged).toEqual({ a: { b: "x", c: "y" }, d: "z" });
    expect(base).toEqual({ a: { b: "x" } });
    expect(part).toEqual({ a: { c: "y" }, d: "z" });
  });
  it("throws naming the dotted key and the source on a duplicate leaf", () => {
    expect(() => mergeTrees({ a: { b: "x" } }, [{ label: "p.json", tree: { a: { b: "y" } } }])).toThrow(/a\.b.*p\.json/);
  });
  it("throws when a leaf and a branch meet", () => {
    expect(() => mergeTrees({ a: "x" }, [{ label: "p.json", tree: { a: { b: "y" } } }])).toThrow(/a.*p\.json/);
    expect(() => mergeTrees({ a: { b: "x" } }, [{ label: "q.json", tree: { a: "y" } }])).toThrow(/a.*q\.json/);
  });
});

describe("merged trees", () => {
  it("equal the Phase 3 files when no area file is present", () => {
    if (AREAS.en.length === 0 && AREAS.zh.length === 0) {
      expect(en).toEqual(baseEn);
      expect(zh).toEqual(baseZh);
    }
    expect(Object.keys(flatten(en)).length).toBeGreaterThanOrEqual(Object.keys(flatten(baseEn as Tree)).length);
  });
  it("lists the same area file names in en and zh", () => {
    expect(AREAS.en).toEqual(AREAS.zh);
  });
  it("has parity per area pair and never redefines a base key", () => {
    const base = flatten(baseEn as Tree);
    for (const name of AREAS.en) {
      const a = flatten(AREAS.trees.en[name] as Tree);
      const b = flatten(AREAS.trees.zh[name] as Tree);
      expect(diffLocales(a, b), name).toEqual({ missingInA: [], missingInB: [], empty: [], placeholderMismatch: [] });
      expect(Object.keys(a).filter((k) => k in base), name).toEqual([]);
    }
  });
});
