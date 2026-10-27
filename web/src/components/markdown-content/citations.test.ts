import { describe, expect, it } from "vitest";
import { holdBackTail, linkMarkers, markerPattern } from "./citations";

describe("streaming citation tails", () => {
  it.each(["#", "##", "##1", "##1$"])("holds the incomplete tail %s", (tail) => expect(holdBackTail(`answer ${tail}`, true)).toEqual({ shown: "answer ", held: tail }));
  it.each(["###", "####", "##1$$", "answer"])("keeps complete text %s", (value) => expect(holdBackTail(value, true)).toEqual({ shown: value, held: "" }));
  it("does not hold final text", () => expect(holdBackTail("answer ##1$", false)).toEqual({ shown: "answer ##1$", held: "" }));
  it("reassembles a marker split across deltas", () => expect(linkMarkers(holdBackTail("answer ##1$" + "$", true).shown, new Set([1]))).toBe("answer [1](#cite-1)"));
});
describe("marker linking outside code", () => {
  const known = new Set([0, 3]);
  it("links sparse reference indices without renumbering", () => expect(linkMarkers("one##0$$ four##3$$", known)).toBe("one[0](#cite-0) four[3](#cite-3)"));
  it("deletes unknown indices", () => expect(linkMarkers("one##2$$", known)).toBe("one"));
  it("retains known unavailable indices for an inert pill", () => expect(linkMarkers("##3$$", known)).toBe("[3](#cite-3)"));
  it("keeps adjacent markers adjacent", () => expect(linkMarkers("##0$$##3$$", known)).toBe("[0](#cite-0)[3](#cite-3)"));
  it("supports CJK text", () => expect(linkMarkers("答案##3$$。", known)).toBe("答案[3](#cite-3)。"));
  it.each(["`##0$$`", "``literal ` ##0$$``", "```txt\n##0$$\n```", "~~~\n##0$$\n~~~", "```\n##0$$"])("leaves markers inside code untouched: %s", (value) => expect(linkMarkers(value, known)).toBe(value));
  it("links prose after a closed fence", () => expect(linkMarkers("```\n##0$$\n```\nanswer##3$$", known)).toBe("```\n##0$$\n```\nanswer[3](#cite-3)"));
  it("handles a long text as one forward scan", () => {
    const value = "passage ".repeat(1250) + "##0$$";
    expect(linkMarkers(value, known)).toBe("passage ".repeat(1250) + "[0](#cite-0)");
  });
  it("returns a fresh shared marker regex", () => {
    const first = markerPattern(); first.exec("##0$$"); expect(markerPattern().exec("##3$$")?.[1]).toBe("3");
  });
});
