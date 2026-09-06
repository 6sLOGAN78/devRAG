import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import remarkCitations from './remark-citations';
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github.css';

interface CitationData {
  chunk_id: string;
  document_id: string;
  content: string;
  source: string;
  page?: number;
  bbox?: number[];
  score?: number;
}

interface MarkdownContentProps {
  content: string;
  citations?: CitationData[] | null;
  onCitationClick?: (index: number) => void;
}

export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, citations, onCitationClick }) => {
  return (
    <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert 
      prose-p:leading-relaxed prose-pre:bg-gray-50 prose-pre:text-gray-900 prose-pre:border
      prose-a:text-blue-600 hover:prose-a:text-blue-500
      prose-headings:font-semibold">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkCitations]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
          // @ts-ignore custom element
          citation: ({ node, ...props }: any) => {
            const idxStr = props.citationindex;
            const idx = parseInt(idxStr, 10);
            if (!citations || isNaN(idx) || idx <= 0 || idx > citations.length) {
              return <span>[{idxStr || ''}]</span>;
            }
            return (
              <button
                onClick={() => onCitationClick?.(idx - 1)}
                className="inline-flex items-center justify-center w-5 h-5 mx-0.5 text-xs font-semibold text-blue-700 bg-blue-100 rounded hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer align-text-top"
                aria-label={`View citation ${idx}`}
              >
                {idx}
              </button>
            );
          },
          a: ({ node, children, href, ...props }) => {
            const isUnsafe = href === '' || href?.startsWith('javascript:') || href?.startsWith('data:');
            return isUnsafe ? (
              <span className="text-red-500 cursor-not-allowed" title="Blocked unsafe link">{children}</span>
            ) : (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
            );
          },
          pre: ({ node, children, ...props }) => (
            <div className="relative group">
              <pre {...props} className="overflow-x-auto p-4 rounded-lg bg-gray-50 border text-sm">
                {children}
              </pre>
            </div>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
