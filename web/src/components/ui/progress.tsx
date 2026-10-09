import { cn } from "@/lib/utils";

export interface ProgressProps {
  /** 0 to 100; anything else is clamped, NaN counts as 0. */
  value: number;
  /** Accessible name of the bar. */
  label: string;
  /** Spoken in place of the number (for example "Finishing"). */
  valueText?: string;
  className?: string;
  "data-testid"?: string;
}

/**
 * Determinate progress bar: an 8 px track and a fill. The width change is smoothed with a short transition that is
 * turned off under reduced motion. The bar carries no text; the row that owns it says the state in words.
 */
export function Progress({ value, label, valueText, className, "data-testid": testId }: ProgressProps) {
  const clamped = Number.isFinite(value) ? Math.min(100, Math.max(0, Math.round(value))) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      aria-valuetext={valueText}
      data-testid={testId}
      className={cn("h-2 w-full overflow-hidden rounded bg-border", className)}
    >
      <div className="h-full bg-primary transition-[width] duration-150 motion-reduce:transition-none" style={{ width: `${clamped}%` }} />
    </div>
  );
}
