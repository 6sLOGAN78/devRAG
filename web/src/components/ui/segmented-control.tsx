import * as React from "react";
import { cn } from "@/lib/utils";

export interface SegmentedOption {
  value: string;
  label: string;
}

export interface SegmentedControlProps {
  /** Accessible name of the group; visually hidden. */
  legend: string;
  /** Shared `name` of the radios; arrow keys move between segments natively. */
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly SegmentedOption[];
  disabled?: boolean;
  className?: string;
  /** Test id of the group; each radio gets `<testId>-<value>`. */
  testId?: string;
}

/** A row of native radios drawn as segments. The selected one gets a foreground border and the page background. */
export function SegmentedControl({ legend, name, value, onChange, options, disabled = false, className, testId }: SegmentedControlProps) {
  const base = React.useId();
  return (
    <fieldset data-testid={testId} className={cn("inline-flex h-10 items-stretch rounded-md border border-input bg-muted p-0.5", className)} disabled={disabled}>
      <legend className="sr-only">{legend}</legend>
      {options.map((option, index) => {
        const id = `${base}-${index}`;
        const checked = option.value === value;
        return (
          <label
            key={option.value}
            htmlFor={id}
            className={cn(
              "flex min-w-16 cursor-pointer items-center justify-center rounded border px-3 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
              checked ? "border-foreground bg-background font-semibold text-foreground" : "border-transparent text-muted-foreground",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <input id={id} data-testid={testId === undefined ? undefined : `${testId}-${option.value}`} type="radio" name={name} value={option.value} checked={checked} onChange={() => onChange(option.value)} className="sr-only" />
            {option.label}
          </label>
        );
      })}
    </fieldset>
  );
}
