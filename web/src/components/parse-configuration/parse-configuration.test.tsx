import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import { Form } from "@/components/ui/form";
import { ParseConfiguration } from ".";
import { fromEscaped, toEscaped } from "./delimiters";
import { chunkFormSchema, type ChunkFormInput } from "./schema";

const VALID = { method: "m", chunkSize: "512", delimiters: "\\n", overlap: "0" };

function parse(over: Partial<Record<keyof ChunkFormInput, unknown>>) {
  return chunkFormSchema.safeParse({ ...VALID, ...over });
}

function messageOf(over: Partial<Record<keyof ChunkFormInput, unknown>>, path: string): string | undefined {
  const result = parse(over);
  if (result.success) return undefined;
  return result.error.issues.find((issue) => issue.path[0] === path)?.message;
}

describe("delimiter conversion", () => {
  it("shows a line break as \\n and takes it back", () => {
    expect(toEscaped("\n!?")).toBe("\\n!?");
    expect(fromEscaped("\\n!?")).toBe("\n!?");
  });

  it("converts \\t to a tab and \\\\ to one backslash", () => {
    expect(fromEscaped("\\t")).toBe("\t");
    expect(fromEscaped("\\\\")).toBe("\\");
    expect(toEscaped("\t")).toBe("\\t");
    expect(toEscaped("\\")).toBe("\\\\");
  });

  it("keeps a lone trailing backslash and an unknown escape as typed", () => {
    expect(fromEscaped("a\\")).toBe("a\\");
    expect(fromEscaped("\\x")).toBe("\\x");
  });

  it("round-trips 200 random strings of the allowed characters", () => {
    const alphabet = ["\n", "\t", "\\", "n", "t", "!", "?", ";", "。", " ", "a"];
    let seed = 12345;
    const next = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed;
    };
    for (let run = 0; run < 200; run += 1) {
      const length = next() % 12;
      let text = "";
      for (let index = 0; index < length; index += 1) text += alphabet[next() % alphabet.length];
      expect(fromEscaped(toEscaped(text))).toBe(text);
    }
  });
});

describe("parse configuration schema", () => {
  it("accepts the defaults and coerces strings to numbers", () => {
    const result = parse({});
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).toMatchObject({ chunkSize: 512, delimiters: "\n", overlap: 0 });
  });

  it("accepts numbers as well as strings", () => {
    expect(parse({ chunkSize: 1, overlap: 50 }).success).toBe(true);
    expect(parse({ chunkSize: "8192" }).success).toBe(true);
  });

  it.each(["0", "8193", "1.5", "", "abc"])("refuses chunk size %j with sizeRange", (value) => {
    expect(messageOf({ chunkSize: value }, "chunkSize")).toBe("errors.chunking.sizeRange");
  });

  it("refuses an empty delimiter and one over 64 characters after conversion", () => {
    expect(messageOf({ delimiters: "" }, "delimiters")).toBe("errors.chunking.delimitersRequired");
    expect(messageOf({ delimiters: "a".repeat(65) }, "delimiters")).toBe("errors.chunking.delimitersMax");
    expect(parse({ delimiters: "a".repeat(64) }).success).toBe(true);
    // 33 escaped line breaks are 66 typed characters but 33 real ones.
    expect(parse({ delimiters: "\\n".repeat(33) }).success).toBe(true);
    expect(messageOf({ delimiters: "\\n".repeat(65) }, "delimiters")).toBe("errors.chunking.delimitersMax");
  });

  it.each(["-1", "51", "2.5", ""])("refuses overlap %j with overlapRange", (value) => {
    expect(messageOf({ overlap: value }, "overlap")).toBe("errors.chunking.overlapRange");
  });
});

function Probe({ initial = VALID }: { initial?: ChunkFormInput }) {
  const form = useForm<ChunkFormInput>({ resolver: zodResolver(chunkFormSchema, undefined, { raw: true }), defaultValues: initial });
  return (
    <Form {...form}>
      <form>
        <ParseConfiguration control={form.control} />
      </form>
    </Form>
  );
}

describe("ParseConfiguration", () => {
  it("offers one-based PDF page selection and validates ranges", async () => {
    render(<Probe />);
    expect(screen.getByLabelText("PDF pages")).toBeInTheDocument();
    const result = parse({ pageRanges: "2-4, 13-30" });
    expect(result.success && result.data.pageRanges).toEqual([[2, 4], [13, 30]]);
    expect(parse({ pageRanges: "0-3" }).success).toBe(false);
    expect(parse({ pageRanges: "9-3" }).success).toBe(false);
    expect(parse({ pageRanges: "" }).success).toBe(true);
  });
  it("offers a working layout checkbox with a persisted boolean value", async () => {
    render(<Probe />);
    const input = screen.getByRole("checkbox", { name: "Use layout analysis" });
    expect(input).toBeChecked();
    await userEvent.click(input);
    expect(input).not.toBeChecked();
    const result = parse({ layoutRecognize: false });
    expect(result.success && result.data.layoutRecognize).toBe(false);
  });
  it("renders the three fields with labels, helpers and a Mono delimiter input", () => {
    render(<Probe />);
    expect(screen.getByLabelText("Chunk size (tokens)")).toHaveValue(512);
    expect(screen.getByText("The largest size of one chunk. The default is 512.")).toBeInTheDocument();
    const delimiters = screen.getByLabelText("Delimiters");
    expect(delimiters).toHaveValue("\\n");
    expect(delimiters).toHaveClass("font-mono");
    expect(screen.getByText("A chunk ends early at any of these characters. Write \\n for a line break.")).toBeInTheDocument();
    expect(screen.getByLabelText("Overlap (%)")).toHaveValue(0);
    expect(screen.getByTestId("field-chunk-size")).toHaveAttribute("inputmode", "numeric");
  });

  it("offers bounded keyword and question counts with off defaults", () => {
    render(<Probe />);
    expect(screen.getByTestId("field-auto-keywords")).toHaveValue(0);
    expect(screen.getByTestId("field-auto-keywords")).toHaveAttribute("max", "32");
    expect(screen.getByTestId("field-auto-questions")).toHaveValue(0);
    expect(screen.getByTestId("field-auto-questions")).toHaveAttribute("max", "16");
    expect(screen.queryByTestId("parse-config-unavailable")).toBeNull();
  });

  it("shows a range message under the field after an invalid entry", async () => {
    const user = userEvent.setup();
    function Submitting() {
      const form = useForm<ChunkFormInput>({ resolver: zodResolver(chunkFormSchema, undefined, { raw: true }), defaultValues: VALID });
      return (
        <Form {...form}>
          <form noValidate onSubmit={form.handleSubmit(() => {})}>
            <ParseConfiguration control={form.control} />
            <button type="submit">go</button>
          </form>
        </Form>
      );
    }
    render(<Submitting />);
    await user.clear(screen.getByTestId("field-chunk-size"));
    await user.type(screen.getByTestId("field-chunk-size"), "9000");
    await user.click(screen.getByRole("button", { name: "go" }));
    expect(await screen.findByText("Enter a whole number from 1 to 8192.")).toBeInTheDocument();
  });
});
