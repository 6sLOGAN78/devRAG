/**
 * Builders for the documents the live ingestion journeys upload (plan 04-27, extended by plan 04-34).
 */

/** Words of filler per paragraph: with the marker word the paragraph is about 303 tokens. */
const FILLER_WORDS = 300;

/**
 * A TXT whose chunk count is known exactly. Paragraph `i` is the marker word `para{i:04d}` followed by `the` repeated
 * 300 times; paragraphs are separated by one blank line. Two such paragraphs never fit the default 512-token budget,
 * so every paragraph becomes exactly one chunk.
 */
export function textFile(paragraphs: number, name = "notes.txt"): File {
  const blocks: string[] = [];
  for (let index = 0; index < paragraphs; index += 1) {
    blocks.push(`para${String(index).padStart(4, "0")} ${Array.from({ length: FILLER_WORDS }, () => "the").join(" ")}`);
  }
  return new File([blocks.join("\n\n")], name, { type: "text/plain" });
}
