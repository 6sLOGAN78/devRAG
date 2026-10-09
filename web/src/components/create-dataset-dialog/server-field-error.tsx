import { CircleAlert } from "lucide-react";
import { useFormField } from "@/components/ui/form";

/**
 * A server answer shown under its field, in the same place and style as `FormMessage`. `FormMessage` translates a locale
 * key and cannot fill in the dataset name, so the caller passes the finished sentence; it is rendered as a text node.
 * The id is the one the control's `aria-describedby` already points at while the field is in error.
 */
export function ServerFieldError({ text }: { text: string | null }) {
  const { formMessageId } = useFormField();
  if (text === null) return null;
  return (
    <p id={formMessageId} role="alert" className="flex items-start gap-1 text-xs font-normal text-destructive">
      <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
}
