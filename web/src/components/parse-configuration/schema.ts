import { z } from "zod";
import { CHUNK_SIZE_MAX, CHUNK_SIZE_MIN, DELIMITERS_MAX, OVERLAP_MAX, OVERLAP_MIN } from "@/constants/chunk-methods";
import { fromEscaped } from "./delimiters";

/** A number typed into an input: '' and non-numbers fail with the field's own message, a string is coerced. */
function whole(min: number, max: number, message: string) {
  return z
    .union([z.string(), z.number()])
    .transform((value) => (typeof value === "string" ? (value.trim() === "" ? Number.NaN : Number(value)) : value))
    .pipe(z.number({ invalid_type_error: message, required_error: message }).int(message).min(min, message).max(max, message));
}

/**
 * The three settings of the General method. Messages are locale keys, translated by `FormMessage`. The ranges equal the
 * server's `ParserConfig`. The delimiters are typed escaped and leave the schema as the real characters.
 */
export const parseConfigSchema = z.object({
  chunkSize: whole(CHUNK_SIZE_MIN, CHUNK_SIZE_MAX, "errors.chunking.sizeRange"),
  delimiters: z
    .string()
    .superRefine((text, context) => {
      const length = [...fromEscaped(text)].length;
      if (length === 0) context.addIssue({ code: z.ZodIssueCode.custom, message: "errors.chunking.delimitersRequired" });
      else if (length > DELIMITERS_MAX) context.addIssue({ code: z.ZodIssueCode.custom, message: "errors.chunking.delimitersMax" });
    })
    .transform(fromEscaped),
  overlap: whole(OVERLAP_MIN, OVERLAP_MAX, "errors.chunking.overlapRange"),
});

/** What the inputs hold (strings) and what a valid submit carries (numbers, real delimiter characters). */
export type ParseConfigInput = z.input<typeof parseConfigSchema>;
export type ParseConfigValues = z.output<typeof parseConfigSchema>;
export type ParseConfigField = keyof ParseConfigInput;

/**
 * The whole dialog form: the chosen method (empty while a stored unbuilt method leaves no radio selected) and the
 * settings. Whether the method may be saved is decided by the form from `IMPLEMENTED`, not by a message.
 */
export const chunkFormSchema = parseConfigSchema.extend({ method: z.string() });

export type ChunkFormInput = z.input<typeof chunkFormSchema>;
export type ChunkFormValues = z.output<typeof chunkFormSchema>;
