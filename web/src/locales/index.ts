/// <reference types="vite/client" />
import baseEn from "./en.json";
import baseZh from "./zh.json";

export type Tree = { [k: string]: string | Tree };

const isTree = (v: unknown): v is Tree => typeof v === "object" && v !== null && !Array.isArray(v);

function mergeInto(target: Tree, source: Tree, label: string, prefix: string): void {
  for (const [k, v] of Object.entries(source)) {
    const key = prefix ? `${prefix}.${k}` : k;
    const existing = target[k];
    if (typeof v === "string") {
      if (existing !== undefined) throw new Error(`duplicate locale key "${key}" in ${label}`);
      target[k] = v;
    } else if (isTree(v)) {
      if (existing === undefined) target[k] = {};
      else if (typeof existing === "string") throw new Error(`locale key "${key}" is a string elsewhere and a group in ${label}`);
      mergeInto(target[k] as Tree, v, label, key);
    } else {
      throw new Error(`locale key "${key}" in ${label} is neither a string nor a group`);
    }
  }
}

/** Deep-merge area trees onto a base. A key defined twice is an error. Sources are copied, never mutated or evaluated. */
export function mergeTrees(base: Tree, parts: ReadonlyArray<{ label: string; tree: Tree }>): Tree {
  const out: Tree = {};
  mergeInto(out, base, "base", "");
  for (const part of parts) mergeInto(out, part.tree, part.label, "");
  return out;
}

const enFiles = import.meta.glob<Tree>("./areas/en/*.json", { eager: true, import: "default" });
const zhFiles = import.meta.glob<Tree>("./areas/zh/*.json", { eager: true, import: "default" });

const nameOf = (path: string) => path.slice(path.lastIndexOf("/") + 1);

function collect(files: Record<string, Tree>) {
  const paths = Object.keys(files).sort();
  const trees: Record<string, Tree> = {};
  for (const p of paths) trees[nameOf(p)] = files[p] as Tree;
  return { names: paths.map(nameOf), trees, parts: paths.map((p) => ({ label: p, tree: files[p] as Tree })) };
}

const enAreas = collect(enFiles);
const zhAreas = collect(zhFiles);

export const AREAS = {
  en: enAreas.names,
  zh: zhAreas.names,
  trees: { en: enAreas.trees, zh: zhAreas.trees },
};

export const en = mergeTrees(baseEn as Tree, enAreas.parts) as Tree & typeof baseEn;
export const zh = mergeTrees(baseZh as Tree, zhAreas.parts) as Tree & typeof baseZh;
