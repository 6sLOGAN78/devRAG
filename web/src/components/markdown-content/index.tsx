import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReferenceChunk } from "@/services/chat-service";
import { CitationPill } from "./citation-pill";
import { CodeBlock } from "./code-block";
import { holdBackTail, linkMarkers } from "./citations";

interface Props {
  text: string;
  chunks: ReferenceChunk[] | null;
  streaming?: boolean;
  openIndex?: number | null;
  onOpenSource: (index: number, element: HTMLElement) => void;
}
function externalLink(href: string): boolean {
  if (!/^https?:\/\//i.test(href) && !/^mailto:[^\s]+/i.test(href)) return false;
  try { return ["http:", "https:", "mailto:"].includes(new URL(href).protocol); } catch { return false; }
}
function imageName(src: string): string {
  const name = src.split(/[?#]/)[0]?.split("/").pop() ?? "";
  try { return decodeURIComponent(name); } catch { return name; }
}
export function MessageMarkdown({ text, chunks, streaming = false, openIndex = null, onOpenSource }: Props) {
  const references = new Map((chunks ?? []).map((chunk) => [chunk.index, chunk]));
  const answer = linkMarkers(holdBackTail(text, streaming).shown, new Set(references.keys()));
  const heading = "mb-2 mt-2 text-base font-semibold";
  const components: Components = {
    a({ href = "", children }) {
      const match = /^#cite-(\d+)$/.exec(href), chunk = match ? references.get(Number(match[1])) : undefined;
      if (match) return chunk ? <CitationPill chunk={chunk} open={openIndex === chunk.index} onOpenSource={onOpenSource} /> : null;
      return externalLink(href) ? <a href={href} target="_blank" rel="noopener noreferrer" className="text-foreground underline underline-offset-4">{children}</a> : <>{children}</>;
    },
    img({ alt, src }) { return <>{alt || imageName(src ?? "")}</>; },
    pre({ children }) { return <CodeBlock>{children}</CodeBlock>; },
    code({ children }) { return <code className="rounded bg-muted px-1 font-mono text-sm">{children}</code>; },
    table({ children }) { return <div className="my-2 overflow-x-auto"><table className="w-full border-collapse text-base">{children}</table></div>; },
    th({ children }) { return <th className="border-b px-3 py-2 text-left text-xs font-semibold">{children}</th>; },
    td({ children }) { return <td className="border-b px-3 py-2 align-top">{children}</td>; },
    h1({ children }) { return <h1 className={heading}>{children}</h1>; },
    h2({ children }) { return <h2 className={heading}>{children}</h2>; },
    h3({ children }) { return <h3 className={heading}>{children}</h3>; },
    h4({ children }) { return <h4 className={heading}>{children}</h4>; },
    h5({ children }) { return <h5 className={heading}>{children}</h5>; },
    h6({ children }) { return <h6 className={heading}>{children}</h6>; },
    p({ children }) { return <p className="mb-2 last:mb-0">{children}</p>; },
    ul({ children }) { return <ul className="mb-2 list-disc pl-6">{children}</ul>; },
    ol({ children }) { return <ol className="mb-2 list-decimal pl-6">{children}</ol>; },
    blockquote({ children }) { return <blockquote className="my-2 border-l-2 pl-4 text-muted-foreground">{children}</blockquote>; },
  };
  return <div className="min-w-0 break-words text-base leading-relaxed"><ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{answer}</ReactMarkdown></div>;
}
