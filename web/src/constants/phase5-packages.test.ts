import { describe, expect, it } from "vitest";
import pkg from "../../package.json";

// Approved by the user at the plan 05-14 checkpoint; mirrored in 05-PACKAGES.md.
const APPROVED = {
  "eventsource-parser": "4.1.2",
  "react-markdown": "10.1.0",
  "remark-gfm": "4.0.1"
};
const BASELINE = [
  "@hookform/resolvers",
  "@radix-ui/react-alert-dialog",
  "@radix-ui/react-dialog",
  "@radix-ui/react-dropdown-menu",
  "@radix-ui/react-label",
  "@radix-ui/react-separator",
  "@radix-ui/react-slot",
  "@radix-ui/react-tooltip",
  "@tanstack/react-query",
  "axios",
  "class-variance-authority",
  "clsx",
  "i18next",
  "lucide-react",
  "react",
  "react-dom",
  "react-hook-form",
  "react-i18next",
  "react-router",
  "sonner",
  "tailwind-merge",
  "tailwindcss-animate",
  "zod",
  "zustand"
];
const FORBIDDEN = [
  "rehype-raw",
  "remark-math",
  "rehype-katex",
  "katex",
  "dompurify",
  "react-syntax-highlighter",
  "react-pdf-highlighter",
  "pdfjs-dist",
  "@tanstack/react-table",
  "react-dropzone",
  "@radix-ui/react-slider",
  "@radix-ui/react-switch",
  "antd"
];

describe("Phase 5 approved dependencies", () => {
  it("adds exactly the approved packages to the existing dependency set", () => {
    expect(Object.keys(pkg.dependencies).sort()).toEqual([...BASELINE, ...Object.keys(APPROVED)].sort());
    for (const [name, version] of Object.entries(APPROVED)) {
      expect((pkg.dependencies as Record<string, string>)[name]).toBe(version);
    }
  });

  it("keeps every dependency pinned to an exact version", () => {
    for (const [name, version] of Object.entries({ ...pkg.dependencies, ...pkg.devDependencies })) {
      expect(version, name).toMatch(/^\d+\.\d+\.\d+(?:-[\w.-]+)?$/);
    }
  });

  it("does not add packages outside the approved Markdown and SSE scope", () => {
    const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    for (const name of FORBIDDEN) expect(names).not.toContain(name);
  });
});
