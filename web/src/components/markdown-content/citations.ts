/** A fresh instance prevents a previous match's lastIndex from leaking into another render. */
export const MARKER_PATTERN = /##(\d+)\$\$/g;
export const markerPattern = (): RegExp => new RegExp(MARKER_PATTERN.source, MARKER_PATTERN.flags);

export function holdBackTail(text: string, streaming: boolean): { shown: string; held: string } {
  if (!streaming) return { shown: text, held: "" };
  const match = /#{1,2}\d*\$?$/.exec(text);
  // A longer hash run is a Markdown heading rather than an incomplete citation.
  if (!match || text[match.index - 1] === "#") return { shown: text, held: "" };
  return { shown: text.slice(0, match.index), held: match[0] };
}

/** Scan fences and backtick spans once. Only prose segments are passed to the shared marker regex. */
export function linkMarkers(text: string, knownIndexes: ReadonlySet<number>): string {
  let fence = "", fenceLength = 0, inlineLength = 0;
  const replace = (prose: string) => prose.replace(markerPattern(), (_raw, digits: string) => {
    const index = Number(digits);
    return knownIndexes.has(index) ? `[${index}](#cite-${index})` : "";
  });
  return text.split("\n").map((line) => {
    const boundary = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      if (boundary && boundary[1]![0] === fence && boundary[1]!.length >= fenceLength && boundary[2]!.trim() === "") { fence = ""; fenceLength = 0; }
      return line;
    }
    if (boundary && inlineLength === 0) { fence = boundary[1]![0]!; fenceLength = boundary[1]!.length; return line; }
    return line.split(/(`+)/).map((part) => {
      if (part.startsWith("`")) {
        if (inlineLength === 0) inlineLength = part.length;
        else if (inlineLength === part.length) inlineLength = 0;
        return part;
      }
      return inlineLength === 0 ? replace(part) : part;
    }).join("");
  }).join("\n");
}
