/**
 * Builders for the documents the live ingestion journeys upload (plan 04-27, extended by plan 04-34).
 */

/** Words of filler per paragraph: with the marker word the paragraph is about 303 tokens. */
const FILLER_WORDS = 300;

/**
 * A TXT whose chunk count is known exactly. Paragraph `i` is the marker word `para{i:04d}` followed by `the` repeated
 * 300 times; paragraphs are separated by one blank line. Two such paragraphs never fit the default 512-token budget,
 * so every paragraph becomes exactly one chunk.
 */
export function textFile(paragraphs: number, name = "notes.txt"): File {
  const blocks: string[] = [];
  for (let index = 0; index < paragraphs; index += 1) {
    blocks.push(`para${String(index).padStart(4, "0")} ${Array.from({ length: FILLER_WORDS }, () => "the").join(" ")}`);
  }
  return new File([blocks.join("\n\n")], name, { type: "text/plain" });
}

// --- PDF and damaged-office builders (plan 04-34): hand-written bytes, no package, ported from test/helpers/pdf_files.py ---

function latin1(text: string): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(new ArrayBuffer(text.length));
  for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index) & 0xff;
  return bytes;
}

function escapePdf(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function pageContent(lines: readonly string[], height: number): string {
  const ops = ["BT", "/F1 12 Tf", "16 TL", `72 ${height - 72} Td`];
  for (const line of lines) ops.push(`(${escapePdf(line)}) Tj T*`);
  ops.push("ET");
  return ops.join("\n");
}

/** A page is a list of text lines, or null for a page with no content stream (nothing to read). */
export type PdfPage = readonly string[] | null;

/** The bytes of a valid single-font PDF: catalog, page tree, Helvetica, one object per page and per content stream, and an xref table. */
export function textPdfBytes(pages: readonly PdfPage[]): Uint8Array<ArrayBuffer> {
  const height = 842;
  const objects = new Map<number, string>();
  const kids: number[] = [];
  let next = 4;
  for (const page of pages) {
    const pageId = next;
    next += 1;
    kids.push(pageId);
    let extra = "";
    if (page !== null) {
      const contentId = next;
      next += 1;
      const stream = pageContent(page, height);
      objects.set(contentId, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
      extra = ` /Contents ${contentId} 0 R`;
    }
    objects.set(pageId, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>${extra} >>`);
  }
  objects.set(1, "<< /Type /Catalog /Pages 2 0 R >>");
  objects.set(2, `<< /Type /Pages /Kids [${kids.map((kid) => `${kid} 0 R`).join(" ")}] /Count ${pages.length} >>`);
  objects.set(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  let out = "%PDF-1.4\n";
  const offsets = new Map<number, number>();
  for (const id of [...objects.keys()].sort((a, b) => a - b)) {
    offsets.set(id, out.length);
    out += `${id} 0 obj\n${objects.get(id)}\nendobj\n`;
  }
  const xref = out.length;
  const size = Math.max(...objects.keys()) + 1;
  out += `xref\n0 ${size}\n0000000000 65535 f \n`;
  for (let id = 1; id < size; id += 1) out += `${String(offsets.get(id)).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${size} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return latin1(out);
}

function pdfFile(pages: readonly PdfPage[], name: string): File {
  return new File([textPdfBytes(pages)], name, { type: "application/pdf" });
}

/** A text PDF with the given pages (six short lines each by default). */
export function textPdf(pages: number, name = "pages.pdf"): File {
  return pdfFile(
    Array.from({ length: pages }, (_, page) => Array.from({ length: 6 }, (__, line) => `Page ${page + 1} line ${line + 1} alpha`)),
    name,
  );
}

/** The 13-page PDF of D-16: six lines per page, `Page {p} line {k} alpha`. */
export function thirteenPagePdf(name = "thirteen.pdf"): File {
  return textPdf(13, name);
}

/** A PDF whose pages have no content stream: it parses to no text at all, which fails at once (D-14). */
export function blankPdf(pages = 2, name = "blank.pdf"): File {
  return pdfFile(Array.from({ length: pages }, () => null), name);
}

/** A DOCX that is not one: the zip signature followed by garbage. It fails on every attempt (D-05). */
export function poisonDocx(name = "damaged.docx"): File {
  const garbage = new Uint8Array(new ArrayBuffer(200));
  for (let index = 0; index < garbage.length; index += 1) garbage[index] = (index * 37 + 11) % 256;
  const head = Uint8Array.from([0x50, 0x4b, 0x03, 0x04]);
  return new File([head, garbage], name, { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
}
