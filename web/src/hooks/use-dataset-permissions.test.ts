import { describe, expect, it } from "vitest";
import { canChangeDocument, canRemoveDocument } from "./use-dataset-permissions";

describe("canChangeDocument (D-02, D-10)", () => {
  it("allows the uploader, the dataset creator, owners and admins", () => {
    expect(canChangeDocument("creator", "uploader", "uploader", "normal")).toBe(true);
    expect(canChangeDocument("creator", "uploader", "creator", "normal")).toBe(true);
    expect(canChangeDocument("creator", "uploader", "other", "owner")).toBe(true);
    expect(canChangeDocument("creator", "uploader", "other", "admin")).toBe(true);
  });

  it("refuses another member, a missing user and an empty uploader", () => {
    expect(canChangeDocument("creator", "uploader", "other", "normal")).toBe(false);
    expect(canChangeDocument("creator", "uploader", null, "normal")).toBe(false);
    expect(canChangeDocument("creator", "", "other", "normal")).toBe(false);
    expect(canChangeDocument("creator", "", "", "normal")).toBe(false);
    expect(canChangeDocument("creator", "uploader", "other", "")).toBe(false);
  });

  it("is the delete rule under a second name", () => {
    const roles = ["owner", "admin", "normal", ""];
    const users = [null, "", "creator", "uploader", "other"];
    for (const role of roles)
      for (const user of users)
        for (const doc of ["", "uploader"]) expect(canChangeDocument("creator", doc, user, role)).toBe(canRemoveDocument("creator", doc, user, role));
  });
});
