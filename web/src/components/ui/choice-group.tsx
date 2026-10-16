import * as React from "react";
import { cn } from "@/lib/utils";

export interface ChoiceOption {
  value: string;
  title: string;
  description: string;
  /** The option cannot be picked; a `badge` says why. */
  disabled?: boolean;
  /** Short trailing word (for example "Later"); a disabled radio points at it with `aria-describedby`. */
  badge?: string;
}

export interface ChoiceGroupProps {
  legend: string;
  /** Shared `name` of the radios; arrow keys move between them natively. */
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly ChoiceOption[];
  disabled?: boolean;
  className?: string;
}

/**
 * A fieldset of native radios, one bordered row per option with a title and a description. Selection and the arrow
 * keys are the browser's own radio behaviour; everything shown is rendered as text.
 */
function ChoiceGroup({ legend, name, value, onChange, options, disabled = false, className }: ChoiceGroupProps) {
  const base = React.useId();
  return (
    <fieldset className={cn("grid gap-2", className)} disabled={disabled}>
      <legend className="mb-2 text-sm font-semibold text-foreground">{legend}</legend>
      {options.map((option, index) => {
        const id = `${base}-${index}`;
        const checked = option.value === value;
        const badgeId = `${id}-badge`;
        const optionDisabled = option.disabled === true;
        return (
          <label
            key={option.value}
            htmlFor={id}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-md border bg-background p-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
              checked ? "border-primary" : "border-input",
              (disabled || optionDisabled) && "cursor-not-allowed opacity-50",
            )}
          >
            <input
              id={id}
              type="radio"
              name={name}
              value={option.value}
              checked={checked}
              disabled={optionDisabled}
              aria-describedby={optionDisabled && option.badge ? badgeId : undefined}
              onChange={() => onChange(option.value)}
              className="mt-1 size-4 shrink-0 accent-primary"
            />
            <span className="grid gap-1">
              <span className="text-sm font-semibold text-foreground">{option.title}</span>
              <span className="text-xs font-normal text-muted-foreground">{option.description}</span>
            </span>
            {option.badge ? (
              <span id={badgeId} className="ml-auto shrink-0 rounded border border-input px-2 text-xs font-normal text-muted-foreground">
                {option.badge}
              </span>
            ) : null}
          </label>
        );
      })}
    </fieldset>
  );
}

export { ChoiceGroup };
