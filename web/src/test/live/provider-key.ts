import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The OpenRouter key for the live provider tests (D-01, D-29). It is read, never printed: the value is returned to the
 * caller only, nothing here logs it, and a missing key fails with a fixed message that names the variable and the file,
 * not any value (D-04: the live tier fails, it never skips).
 *
 * Order: the `OPENROUTER_API_KEY` environment variable, else the git-ignored `docker/.env` one level above `web/`.
 */
const NAME = "OPENROUTER_API_KEY";

function fromEnvFile(): string {
  let text = "";
  try {
    text = readFileSync(resolve(process.cwd(), "..", "docker", ".env"), "utf8");
  } catch {
    return "";
  }
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("#") || !trimmed.startsWith(`${NAME}=`)) continue;
    return trimmed
      .slice(NAME.length + 1)
      .trim()
      .replace(/^(["'])(.*)\1$/, "$2");
  }
  return "";
}

export function liveProviderKey(): string {
  const key = (process.env[NAME] ?? "").trim() || fromEnvFile();
  if (key === "") throw new Error(`${NAME} is missing from the environment and from docker/.env; the live Models journey needs it`);
  return key;
}

/** True when `text` ends with the last four characters of `key`. A boolean, so a failed assertion never prints key characters. */
export function endsWithKeyTail(text: string, key: string): boolean {
  return text.trim().endsWith(key.slice(-4));
}

/** True when `haystack` contains the key or a 12-character window of it. A boolean for the same reason. */
export function containsKeyFragment(haystack: string, key: string): boolean {
  if (haystack.includes(key)) return true;
  for (let start = 0; start + 12 <= key.length; start += 1) {
    if (haystack.includes(key.slice(start, start + 12))) return true;
  }
  return false;
}
