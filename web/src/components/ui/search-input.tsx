import { Search, X } from "lucide-react";
import * as React from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface SearchInputProps {
  /** The value the field starts with (and takes again when the parent changes it, for example after a reset). */
  value: string;
  /** Called once, `debounceMs` after typing stops, and at once when the field is cleared. */
  onSearch: (value: string) => void;
  /** Visually hidden label; also the placeholder. */
  label: string;
  clearLabel: string;
  debounceMs?: number;
  className?: string;
  id?: string;
}

/**
 * A search box with a leading icon, a trailing clear button (only while non-empty) and a debounced `onSearch`. The
 * pending timer is cancelled on clear and on unmount, so a stale search never fires afterwards.
 */
function SearchInput({ value, onSearch, label, clearLabel, debounceMs = 300, className, id }: SearchInputProps) {
  const generated = React.useId();
  const fieldId = id ?? generated;
  const [text, setText] = React.useState(value);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const onSearchRef = React.useRef(onSearch);
  onSearchRef.current = onSearch;

  const cancel = React.useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  React.useEffect(() => setText(value), [value]);
  React.useEffect(() => cancel, [cancel]);

  const change = (next: string) => {
    setText(next);
    cancel();
    timer.current = setTimeout(() => {
      timer.current = null;
      onSearchRef.current(next);
    }, debounceMs);
  };

  const clear = () => {
    cancel();
    setText("");
    onSearchRef.current("");
    inputRef.current?.focus();
  };

  return (
    <div className={cn("relative", className)}>
      <label htmlFor={fieldId} className="sr-only">
        {label}
      </label>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
      <Input
        ref={inputRef}
        id={fieldId}
        type="search"
        value={text}
        placeholder={label}
        autoComplete="off"
        className="pl-9 pr-10 [&::-webkit-search-cancel-button]:hidden"
        onChange={(event) => change(event.target.value)}
      />
      {text !== "" ? (
        <button
          type="button"
          aria-label={clearLabel}
          onClick={clear}
          className="absolute right-1 top-1/2 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [@media(pointer:coarse)]:size-11"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

export { SearchInput };
