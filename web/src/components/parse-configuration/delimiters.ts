/**
 * Delimiter text as the form shows and types it: a line break is `\n`, a tab is `\t`, a backslash is `\\`. The stored
 * value holds the real characters. A delimiter is a set of characters and is never read as a pattern (T-04-29-01).
 */
export function toEscaped(value: string): string {
  let out = "";
  for (const char of value) {
    if (char === "\\") out += "\\\\";
    else if (char === "\n") out += "\\n";
    else if (char === "\t") out += "\\t";
    else out += char;
  }
  return out;
}

/** The inverse of `toEscaped`. An unknown escape and a lone trailing backslash are kept as typed. */
export function fromEscaped(text: string): string {
  const chars = [...text];
  let out = "";
  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index] as string;
    const next = chars[index + 1];
    if (char === "\\" && next === "n") {
      out += "\n";
      index += 1;
    } else if (char === "\\" && next === "t") {
      out += "\t";
      index += 1;
    } else if (char === "\\" && next === "\\") {
      out += "\\";
      index += 1;
    } else {
      out += char;
    }
  }
  return out;
}
