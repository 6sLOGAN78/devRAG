import { Upload } from "lucide-react";
import { useRef, useState, type ChangeEvent, type DragEvent, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** One thing the user dropped or picked, with the drop handler's verdict on folders. */
export interface DroppedEntry {
  file: File;
  isDirectory: boolean;
}

/** True when a drag carries files; drags of text or links are left alone. */
export function carriesFiles(dataTransfer: Pick<DataTransfer, "types"> | null | undefined): boolean {
  return Array.from(dataTransfer?.types ?? []).includes("Files");
}

/**
 * Reads a drop. A folder is told apart with `webkitGetAsEntry().isDirectory`; where that API is missing, a zero-byte
 * item with no type is treated as a folder. Must run inside the drop event (the entries die afterwards).
 */
export function readDropped(dataTransfer: DataTransfer): DroppedEntry[] {
  const items = Array.from(dataTransfer.items ?? []).filter((item) => item.kind === "file");
  if (items.length > 0) {
    return items.flatMap((item) => {
      const file = item.getAsFile();
      if (!file) return [];
      const hasEntryApi = typeof item.webkitGetAsEntry === "function";
      const entry = hasEntryApi ? item.webkitGetAsEntry() : null;
      return [{ file, isDirectory: entry ? entry.isDirectory : !hasEntryApi && file.size === 0 && file.type === "" }];
    });
  }
  return Array.from(dataTransfer.files ?? []).map((file) => ({ file, isDirectory: false }));
}

export interface DropzoneProps {
  /** Value of the hidden input's `accept`. */
  accept: string;
  /** Accessible name of the region (the dialog's title text; Radix owns the title element's id). */
  label: string;
  onFiles: (entries: DroppedEntry[]) => void;
  chooseRef: RefObject<HTMLButtonElement>;
}

/**
 * The drop target (native drag events, no library). "Choose files" is the keyboard path and opens a hidden file input;
 * the region itself is not focusable. A depth counter keeps the active state through nested enter and leave events.
 */
export function Dropzone({ accept, label, onFiles, chooseRef }: DropzoneProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [active, setActive] = useState(false);

  function enter(event: DragEvent<HTMLDivElement>): void {
    if (!carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    depth.current += 1;
    setActive(true);
  }

  function over(event: DragEvent<HTMLDivElement>): void {
    if (!carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }

  function leave(event: DragEvent<HTMLDivElement>): void {
    if (!carriesFiles(event.dataTransfer)) return;
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setActive(false);
  }

  function drop(event: DragEvent<HTMLDivElement>): void {
    if (!carriesFiles(event.dataTransfer)) return;
    event.preventDefault();
    depth.current = 0;
    setActive(false);
    const entries = readDropped(event.dataTransfer);
    if (entries.length > 0) onFiles(entries);
  }

  function picked(event: ChangeEvent<HTMLInputElement>): void {
    const files = Array.from(event.target.files ?? []);
    // Reset so choosing the same file again fires another change.
    event.target.value = "";
    if (files.length > 0) onFiles(files.map((file) => ({ file, isDirectory: false })));
  }

  return (
    <div
      role="group"
      aria-label={label}
      data-testid="upload-dropzone"
      onDragEnter={enter}
      onDragOver={over}
      onDragLeave={leave}
      onDrop={drop}
      className={cn(
        "flex min-h-40 flex-col items-center justify-center gap-3 rounded-lg border-2 bg-background p-6 text-center",
        active ? "border-solid border-primary" : "border-dashed border-border",
      )}
    >
      <Upload className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-normal">{active ? t("upload.drop.active") : t("upload.drop.idle")}</p>
      <Button type="button" variant="outline" ref={chooseRef} data-testid="upload-choose" onClick={() => inputRef.current?.click()}>
        {t("upload.choose")}
      </Button>
      <input ref={inputRef} type="file" multiple accept={accept} onChange={picked} tabIndex={-1} aria-hidden="true" className="sr-only" data-testid="upload-input" />
    </div>
  );
}
