import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./code-block";

/** Original source Markdown has no citation rewriting, HTML execution or remote media loading. */
const components: Components = {
  img({ alt, src = "" }) { return <span>{alt || src.split(/[?#]/)[0]?.split("/").pop() || ""}</span>; },
  a({ href = "", children }) {
    return /^https?:\/\//i.test(href) || /^mailto:[^\s]+/i.test(href)
      ? <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">{children}</a>
      : <>{children}</>;
  },
  pre({ children }) { return <CodeBlock>{children}</CodeBlock>; },
  code({ children }) { return <code className="rounded bg-muted px-1 font-mono text-sm">{children}</code>; },
  table({ children }) { return <div className="my-2 overflow-x-auto"><table className="w-full border-collapse">{children}</table></div>; },
  th({ children }) { return <th className="border-b px-3 py-2 text-left text-xs font-semibold">{children}</th>; },
  td({ children }) { return <td className="border-b px-3 py-2 align-top">{children}</td>; },
  h1({ children }) { return <h1 className="mb-2 mt-2 text-base font-semibold">{children}</h1>; },
  h2({ children }) { return <h2 className="mb-2 mt-2 text-base font-semibold">{children}</h2>; },
  h3({ children }) { return <h3 className="mb-2 mt-2 text-base font-semibold">{children}</h3>; },
  h4({ children }) { return <h4 className="mb-2 mt-2 text-base font-semibold">{children}</h4>; },
  h5({ children }) { return <h5 className="mb-2 mt-2 text-base font-semibold">{children}</h5>; },
  h6({ children }) { return <h6 className="mb-2 mt-2 text-base font-semibold">{children}</h6>; },
  p({ children }) { return <p className="mb-2 last:mb-0">{children}</p>; },
  ul({ children }) { return <ul className="mb-2 list-disc pl-6">{children}</ul>; },
  ol({ children }) { return <ol className="mb-2 list-decimal pl-6">{children}</ol>; },
};

export function SourceMarkdown({ text }: { text: string }) {
  return <div data-testid="source-markdown" className="min-w-0 whitespace-normal break-words leading-relaxed"><ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown></div>;
}
