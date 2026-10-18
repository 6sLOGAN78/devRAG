import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export interface DiscardChangesDialogProps {
  open: boolean;
  /** Keep editing: the dialog closes and the held action is dropped. */
  onKeep: () => void;
  /** Discard changes: the held action runs. */
  onDiscard: () => void;
  /** Where focus goes when the dialog has closed; the owner returns it to the textarea. */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * "Discard unsaved changes?" (UI-17): a standalone `AlertDialog`, never opened over another dialog. "Keep editing" has the
 * initial focus; a press outside the dialog does not close it. Its content is mounted only while it is open, so it holds
 * nothing from one opening to the next (FE-04).
 */
export function DiscardChangesDialog({ open, onKeep, onDiscard, onCloseAutoFocus }: DiscardChangesDialogProps) {
  const { t } = useTranslation();
  return (
    <AlertDialog open={open} onOpenChange={(next) => !next && onKeep()}>
      <AlertDialogContent data-testid="discard-dialog" onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("inspector.discard.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("inspector.discard.body")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="discard-keep">{t("inspector.discard.keep")}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" data-testid="discard-confirm" onClick={(event) => {
              // The owner closes the dialog by clearing what was held; closing it here would also report "keep".
              event.preventDefault();
              onDiscard();
            }}
          >
            {t("inspector.discard.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
