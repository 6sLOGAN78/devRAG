import { describe, expect, it } from "vitest";
import { canManageAssistant } from "./use-assistant-permissions";

describe("assistant manage permission", () => {
  it.each([
    ["u1", "u1", "normal", "me", true], ["u1", "u1", "normal", "team", true],
    ["other", "u1", "owner", "me", false], ["other", "u1", "owner", "team", true],
    ["other", "u1", "admin", "me", false], ["other", "u1", "admin", "team", true],
    ["other", "u1", "normal", "me", false], ["other", "u1", "normal", "team", false],
    ["", "", "normal", "me", false], ["u1", null, "", "me", false],
  ] as const)("creator=%s caller=%s role=%s visibility=%s => %s", (creator, user, role, permission, allowed) => expect(canManageAssistant(creator, user, role, permission)).toBe(allowed));
});
