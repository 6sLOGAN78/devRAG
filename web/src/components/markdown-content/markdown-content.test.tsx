import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MarkdownContent } from './index';

describe('MarkdownContent Rendering', () => {
  it('renders standard markdown (headings, bold, italics)', () => {
    const { container } = render(<MarkdownContent content="# Hello\n**bold** and *italic*" />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hello');
    expect(container.innerHTML).toContain('<strong>bold</strong>');
    expect(container.innerHTML).toContain('<em>italic</em>');
  });

  it('renders tables', () => {
    const tableMd = `| Metric | Value |\n|---|---:|\n| Accuracy | 95% |`;
    render(<MarkdownContent content={tableMd} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
    expect(screen.getByText('95%')).toBeInTheDocument();
  });

  it('renders lists', () => {
    render(<MarkdownContent content={'* Item 1\n* Item 2'} />);
    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(2);
    expect(listItems[0]).toHaveTextContent('Item 1');
  });

  it('renders safe links and blocks unsafe protocols', () => {
    const md = `[Safe](https://example.com) [Unsafe](javascript:alert('x'))`;
    render(<MarkdownContent content={md} />);
    const safeLink = screen.getByText('Safe');
    expect(safeLink.closest('a')).toHaveAttribute('href', 'https://example.com');
    
    const unsafeText = screen.getByText('Unsafe');
    expect(unsafeText.closest('a')).toBeNull(); // Should be a span not a link
    expect(unsafeText.tagName.toLowerCase()).toBe('span');
  });

  it('renders blockquotes', () => {
    render(<MarkdownContent content="> This is a quote" />);
    expect(screen.getByText('This is a quote').closest('blockquote')).toBeInTheDocument();
  });

  it('renders code blocks and inline code', () => {
    const md = `Inline \`code\`\n\n\`\`\`python\nprint("hello")\n\`\`\``;
    render(<MarkdownContent content={md} />);
    expect(screen.getByText('code').tagName.toLowerCase()).toBe('code');
    const codeBlock = screen.getByText(/print/);
    expect(codeBlock.closest('pre')).toBeInTheDocument();
  });

  it('renders math equations using KaTeX', () => {
    const md = `Math: $E=mc^2$`;
    const { container } = render(<MarkdownContent content={md} />);
    expect(container.querySelector('.katex')).toBeInTheDocument();
  });

  it('does not crash on malformed markdown/math', () => {
    const md = `Math: $\\broken{math$ and \`\`\`python\nincomplete`;
    const { container } = render(<MarkdownContent content={md} />);
    expect(container).toBeInTheDocument();
  });

  it('prevents XSS attacks', () => {
    const md = `<script>alert('xss')</script> <img src=x onerror=alert(1)>`;
    const { container } = render(<MarkdownContent content={md} />);
    expect(container.querySelector('script')).toBeNull();
  });
});

describe('Citation Rendering in MarkdownContent', () => {
  const citations = [{
    chunk_id: '1', document_id: 'doc1', content: 'test chunk', source: 'source1.pdf'
  }];

  it('parses [1] as a clickable citation button', () => {
    const onCitationClick = vi.fn();
    render(<MarkdownContent content="According to [1], this is true." citations={citations} onCitationClick={onCitationClick} />);
    const button = screen.getByRole('button', { name: 'View citation 1' });
    expect(button).toBeInTheDocument();
    
    fireEvent.click(button);
    expect(onCitationClick).toHaveBeenCalledWith(0);
  });

  it('does not parse [2] if out of bounds', () => {
    render(<MarkdownContent content="Out of bounds [2]" citations={citations} />);
    expect(screen.queryByRole('button', { name: 'View citation 2' })).toBeNull();
    expect(screen.getByText(/Out of bounds/)).toBeInTheDocument();
    expect(screen.getByText(/\[2\]/)).toBeInTheDocument();
  });

  it('ignores citations embedded inside code blocks', () => {
    render(<MarkdownContent content={'```text\nInside code [1]\n```'} citations={citations} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('ignores false positive brackets like [normal text]', () => {
    render(<MarkdownContent content="This is [normal text]." citations={citations} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
