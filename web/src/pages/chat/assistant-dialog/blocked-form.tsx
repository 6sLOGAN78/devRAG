import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MODEL_SETTINGS_PATH } from "@/constants/app-paths";

export function BlockedForm({ canManage, onClose }: { canManage: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const action = useRef<HTMLAnchorElement>(null), close = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (canManage) action.current?.focus(); else close.current?.focus(); }, [canManage]);
  return <div data-testid="assistant-blocked" className="flex flex-col gap-4">
    <DialogHeader><DialogTitle>{t("assistant.dialog.blocked.heading")}</DialogTitle><DialogDescription>{t("assistant.dialog.blocked.body")}</DialogDescription></DialogHeader>
    {!canManage ? <p className="text-sm text-muted-foreground">{t("assistant.dialog.blocked.bodyMember")}</p> : null}
    <DialogFooter>
      <DialogClose asChild><Button ref={close} type="button" variant="ghost">{t("dialog.close")}</Button></DialogClose>
      {canManage ? <Button asChild><Link ref={action} to={MODEL_SETTINGS_PATH} onClick={onClose}>{t("assistant.dialog.blocked.action")}</Link></Button> : null}
    </DialogFooter>
  </div>;
}
