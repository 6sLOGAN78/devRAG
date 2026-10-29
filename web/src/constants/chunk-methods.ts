/**
 * Chunking methods in the order of docs/02-frontend/components.md (D-15). Ids live here so no component carries a method
 * name as a literal. `IMPLEMENTED` mirrors the server's `IMPLEMENTED_PARSERS`: only those can be chosen or sent.
 */
export const CHUNK_METHODS = ["naive", "qa", "paper", "book", "laws", "presentation", "table", "manual", "resume", "picture", "email", "tag", "one", "audio"] as const;

export type ChunkMethod = (typeof CHUNK_METHODS)[number];

export const GENERAL_METHOD: ChunkMethod = "naive";

export const IMPLEMENTED: readonly ChunkMethod[] = [GENERAL_METHOD, "one", "manual", "qa", "book", "paper", "laws", "presentation", "table", "picture", "audio", "email", "resume"];

/** The locale stem of a method: `datasets.chunking.method.<stem>` has `.title` and `.body`. */
export const METHOD_STEMS: Readonly<Record<ChunkMethod, string>> = {
  naive: "general",
  qa: "qa",
  paper: "paper",
  book: "book",
  laws: "laws",
  presentation: "presentation",
  table: "table",
  manual: "manual",
  resume: "resume",
  picture: "picture",
  email: "email",
  tag: "tag",
  one: "one",
  audio: "audio",
};

export const isChunkMethod = (value: string): value is ChunkMethod => (CHUNK_METHODS as readonly string[]).includes(value);

export const isImplemented = (value: string): boolean => (IMPLEMENTED as readonly string[]).includes(value);

/** Bounds of the three real settings; the server's `ParserConfig` is authoritative (BE-09, D-31). */
export const CHUNK_SIZE_MIN = 1;
export const CHUNK_SIZE_MAX = 8192;
export const OVERLAP_MIN = 0;
export const OVERLAP_MAX = 50;
export const DELIMITERS_MAX = 64;
