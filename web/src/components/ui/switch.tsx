import { cn } from "@/lib/utils";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Word shown beside the control while it is on (a caller-supplied label). */
  onLabel: string;
  /** Word shown beside the control while it is off. */
  offLabel: string;
  /** A change is in flight: clicks are ignored and `aria-busy` is set. */
  busy?: boolean;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  "data-testid"?: string;
  className?: string;
}

/**
 * Native switch: a visually hidden `input role="switch"` over a styled track. The current state is always said in
 * words beside the track, never by colour alone. Space toggles with the browser's own checkbox behaviour.
 */
export function Switch({ checked, onChange, onLabel, offLabel, busy = false, disabled = false, id, className, "aria-label": ariaLabel, "data-testid": testId }: SwitchProps) {
  const inert = disabled || busy;
  return (
    <label
      className={cn(
        "relative inline-flex min-h-10 items-center gap-2 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
        inert ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <input
        id={id}
        type="checkbox"
        role="switch"
        aria-checked={checked}
        aria-busy={busy ? "true" : undefined}
        aria-label={ariaLabel}
        data-testid={testId}
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          if (busy) return;
          onChange(event.target.checked);
        }}
        className="peer sr-only"
      />
      <span aria-hidden="true" className={cn("relative inline-block h-5 w-9 shrink-0 rounded-full transition-colors motion-reduce:transition-none", checked ? "bg-foreground" : "bg-border")}>
        <span
          className={cn(
            "absolute left-0.5 top-0.5 size-4 rounded-full bg-background transition-transform motion-reduce:transition-none",
            checked ? "translate-x-4" : "translate-x-0",
          )}
        />
      </span>
      <span className="text-xs font-normal text-foreground">{checked ? onLabel : offLabel}</span>
    </label>
  );
}
