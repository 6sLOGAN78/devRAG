import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MODEL_SETTINGS_PATH } from "@/constants/app-paths";

/**
 * The create dialog when the workspace has no default embedding model (D-18). Nothing is guessed or auto-picked: it
 * says what is missing. Owners and admins get a link to model settings; members are told whom to ask and get only Close.
 */
export function BlockedForm({ canManage, onClose }: { canManage: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="create-dataset-blocked" className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{t("datasets.blocked.title")}</DialogTitle>
        <DialogDescription>{t("datasets.blocked.body")}</DialogDescription>
      </DialogHeader>
      {canManage ? null : <p className="text-sm font-normal text-muted-foreground">{t("datasets.blocked.member")}</p>}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="ghost">
            {t("dialog.close")}
          </Button>
        </DialogClose>
        {canManage ? (
          <Button asChild>
            <Link to={MODEL_SETTINGS_PATH} onClick={onClose}>
              {t("datasets.missingDefault.link")}
            </Link>
          </Button>
        ) : null}
      </DialogFooter>
    </div>
  );
}
