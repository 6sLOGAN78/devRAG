import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export interface StopDialogProps {
  open: boolean;
  /** Files that have not finished. */
  count: number;
  /** Dismiss the question (Keep uploading, Escape). */
  onKeep: () => void;
  /** Abort the uploads and close. */
  onStop: () => void;
}

/**
 * "Stop uploading?" (UI-SPEC). It behaves as an alert dialog (role, no corner close, no dismissal by an outside click,
 * default focus on "Keep uploading") but is built on the Dialog primitive on purpose: the shared AlertDialog resolves a
 * second copy of Radix's focus-scope and dismissable-layer packages, so layered over the upload Dialog the two do not
 * see each other and focus is pulled back to the Dialog. Using the Dialog's own copy lets the layers cooperate.
 */
export function StopUploadsDialog({ open, count, onKeep, onStop }: StopDialogProps) {
  const { t } = useTranslation();
  const keepRef = useRef<HTMLButtonElement>(null);
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onKeep();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 motion-reduce:animate-none" />
        <DialogPrimitive.Content
          role="alertdialog"
          data-testid="upload-stop-dialog"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            keepRef.current?.focus();
          }}
          onPointerDownOutside={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
          className="fixed left-1/2 top-1/2 z-50 flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-lg border bg-card p-6 text-card-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 motion-reduce:animate-none"
        >
          <div className="flex flex-col gap-2">
            <DialogPrimitive.Title className="text-xl font-semibold leading-tight">{t("upload.stop.title")}</DialogPrimitive.Title>
            <DialogPrimitive.Description className="text-sm text-muted-foreground">{t("upload.stop.body", { count })}</DialogPrimitive.Description>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" ref={keepRef} data-testid="upload-stop-keep" onClick={onKeep}>
              {t("upload.stop.keep")}
            </Button>
            <Button type="button" variant="destructive" data-testid="upload-stop-confirm" onClick={onStop}>
              {t("upload.stop.confirm")}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
