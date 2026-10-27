import { Label } from "./label";

interface Props {
  id: string; label: string; value: number; onChange: (value: number) => void;
  min: number; max: number; step: number; readout: string; helper?: string;
  lowLabel?: string; highLabel?: string; testId?: string; disabled?: boolean;
}
/** Native keyboard behaviour and a formatted value that is also announced by the range input. */
export function RangeField({ id, label, value, onChange, min, max, step, readout, helper, lowLabel, highLabel, testId, disabled }: Props) {
  return <div className="grid gap-2">
    <div className="flex items-start justify-between gap-4"><Label htmlFor={id}>{label}</Label><span className="min-w-16 text-right text-sm tabular-nums">{readout}</span></div>
    <input id={id} type="range" value={value} min={min} max={max} step={step} disabled={disabled} data-testid={testId}
      aria-valuetext={readout} aria-describedby={helper ? `${id}-help` : undefined}
      onChange={(event) => onChange(Number(event.target.value))} className="h-6 w-full cursor-pointer accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
    {lowLabel || highLabel ? <div className="flex justify-between gap-4 text-xs text-muted-foreground"><span>{lowLabel}</span><span>{highLabel}</span></div> : null}
    {helper ? <p id={`${id}-help`} className="text-xs text-muted-foreground">{helper}</p> : null}
  </div>;
}
