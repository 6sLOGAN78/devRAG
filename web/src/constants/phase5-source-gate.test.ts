/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import pkg from "../../package.json";

const all = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const production = Object.entries(all).filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes("/src/test/"));
const FORBIDDEN = ["dangerouslySetInnerHTML", "iframe", "rehype-raw", "EventSource", "react-pdf-highlighter", "pdfjs-dist", "@tanstack/react-table", "@radix-ui/react-slider", "remark-math", "rehype-katex", "dompurify", "react-syntax-highlighter", "react-dropzone"];
const BASELINE = ["@hookform/resolvers", "@radix-ui/react-alert-dialog", "@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu", "@radix-ui/react-label", "@radix-ui/react-separator", "@radix-ui/react-slot", "@radix-ui/react-tooltip", "@tanstack/react-query", "axios", "class-variance-authority", "clsx", "i18next", "lucide-react", "react", "react-dom", "react-hook-form", "react-i18next", "react-router", "sonner", "tailwind-merge", "tailwindcss-animate", "zod", "zustand"];
const APPROVED = { "eventsource-parser": "4.1.2", "react-markdown": "10.1.0", "remark-gfm": "4.0.1" };
const code = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const testImport = /(?:from|import)\s*\(?\s*["'](?:@\/test(?:\/|["'])|src\/test|\.\/test\/|\.\.\/test\/)/;

describe("Phase 5 source gate", () => {
  it("scans real production files and the new renderer", () => {
    expect(production.length).toBeGreaterThan(80);
    expect(production.some(([path]) => path.endsWith("/markdown-content/index.tsx"))).toBe(true);
  });
  it.each(FORBIDDEN)("keeps %s out of production source", (needle) => {
    expect(production.filter(([, source]) => code(source).includes(needle)).map(([path]) => path)).toEqual([]);
  });
  it("keeps test-server imports out of production", () => {
    expect(production.filter(([, source]) => testImport.test(code(source))).map(([path]) => path)).toEqual([]);
  });
  it("keeps only the approved new packages at exact pins", () => {
    expect(Object.keys(pkg.dependencies).sort()).toEqual([...BASELINE, ...Object.keys(APPROVED)].sort());
    for (const [name, pin] of Object.entries(APPROVED)) expect((pkg.dependencies as Record<string, string>)[name]).toBe(pin);
  });
});
