import { EllipsisVertical, Settings, SlidersHorizontal, Trash2 } from "lucide-react";
import { useRef, type Ref } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

export interface DatasetActionsMenuProps {
  /** The dataset's name, for the trigger's accessible name. User text: rendered through i18n interpolation only. */
  name: string;
  onSettings: () => void;
  /** Opens the default chunking method dialog. The item exists only when this is given. */
  onChunking?: () => void;
  onDelete: () => void;
  /** The trigger button, so the owner of the dialogs can return focus to it when a dialog closes. */
  triggerRef?: Ref<HTMLButtonElement>;
}

/**
 * The per-dataset actions menu (UI-10, D-09): "Dataset settings" and "Delete dataset" (destructive text). The caller
 * draws it only for the dataset's creator and the workspace owner and admins. The trigger sits above the card's link
 * layer (`relative z-10`). After an item is chosen the menu does not hand focus back to the trigger: the dialog that
 * opens takes it, and gives it back to the trigger when it closes.
 */
export function DatasetActionsMenu({ name, onSettings, onChunking, onDelete, triggerRef }: DatasetActionsMenuProps) {
  const { t } = useTranslation();
  const chosen = useRef(false);
  return (
    // Not modal: a modal menu locks the page (pointer-events none on the body) and, when the dialog it opens takes over
    // in the same moment, leaves that lock behind once the dialog closes.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          ref={triggerRef}
          type="button"
          variant="ghost"
          size="icon"
          data-testid="dataset-actions"
          aria-label={t("datasets.card.actions", { name })}
          className="relative z-10"
        >
          <EllipsisVertical aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        data-testid="dataset-menu"
        aria-label={t("datasets.menu.label")}
        onCloseAutoFocus={(event) => {
          if (chosen.current) event.preventDefault();
          chosen.current = false;
        }}
      >
        {onChunking === undefined ? null : (
          <DropdownMenuItem
            data-testid="dataset-menu-chunking"
            onSelect={() => {
              chosen.current = true;
              onChunking();
            }}
          >
            <SlidersHorizontal aria-hidden="true" />
            {t("datasets.menu.chunking")}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          data-testid="dataset-menu-settings"
          onSelect={() => {
            chosen.current = true;
            onSettings();
          }}
        >
          <Settings aria-hidden="true" />
          {t("datasets.menu.settings")}
        </DropdownMenuItem>
        <DropdownMenuItem
          data-testid="dataset-menu-delete"
          className="text-destructive focus:text-destructive"
          onSelect={() => {
            chosen.current = true;
            onDelete();
          }}
        >
          <Trash2 aria-hidden="true" />
          {t("datasets.menu.delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
