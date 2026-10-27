import * as React from "react";
import { cn } from "@/lib/utils";

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Applied through the DOM property: it has no HTML attribute. */
  indeterminate?: boolean;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-describedby"?: string;
  "data-testid"?: string;
  className?: string;
}

/** Native checkbox, a 16 px box inside a 40 px hit area. The tick and border use the foreground colour. */
export function Checkbox({ checked, onChange, indeterminate = false, disabled = false, id, className, "aria-label": ariaLabel, "aria-describedby": describedBy, "data-testid": testId }: CheckboxProps) {
  const ref = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate, checked]);
  return (
    <span className={cn("inline-flex size-10 items-center justify-center", className)}>
      <input
        ref={ref}
        id={id}
        type="checkbox"
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        data-testid={testId}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 cursor-pointer accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
      />
    </span>
  );
}
