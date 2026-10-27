import { useRef, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssistantPermissions } from "@/hooks/use-assistant-permissions";
import { useAssistantRequest } from "@/hooks/use-chat-request";
import { useModelsRequest } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { ApiError } from "@/services/http";
import { AssistantForm, type SavedAssistant } from "./assistant-form";
import { BlockedForm } from "./blocked-form";
import { useAssistantDatasets } from "./dataset-checklist";

export interface AssistantDialogProps {
  open: boolean; onOpenChange: (open: boolean) => void; mode: "create" | "settings"; assistantId?: string;
  onSaved: (value: SavedAssistant) => void; onCloseAutoFocus?: (event: Event) => void;
}
function Header({ settings }: { settings: boolean }) {
  const { t } = useTranslation();
  return <DialogHeader><DialogTitle>{t(settings ? "assistant.dialog.titleSettings" : "assistant.dialog.titleCreate")}</DialogTitle><DialogDescription className="sr-only">{t("assistant.field.datasetsHelp")}</DialogDescription></DialogHeader>;
}
function Body({ props, pendingRef }: { props: AssistantDialogProps; pendingRef: MutableRefObject<boolean> }) {
  const { t } = useTranslation(), workspace = useActiveWorkspace();
  const settings = props.mode === "settings";
  const models = useModelsRequest("chat"), rerankModels = useModelsRequest("rerank");
  const detail = useAssistantRequest(props.assistantId, settings);
  const canManage = useAssistantPermissions(detail.data);
  const datasets = useAssistantDatasets(models.data !== undefined && models.data.length > 0);
  const close = () => props.onOpenChange(false);
  const retryModels = () => Promise.all([models.refetch(), rerankModels.refetch()]);
  if ((models.isError && !models.data) || (rerankModels.isError && !rerankModels.data)) return <><Header settings={settings} /><ErrorState heading={t("assistant.dialog.modelsError")} onAction={() => void retryModels()} /></>;
  if (settings && detail.isError && !detail.data) return <><Header settings /><ErrorState heading={detail.error instanceof ApiError && detail.error.status === 404 ? t("assistant.error.gone") : undefined} noun={t("assistant.dialog.titleSettings")} onAction={() => void detail.refetch()} /></>;
  if (models.data?.length === 0) return <BlockedForm canManage={workspace?.role === "owner" || workspace?.role === "admin"} onClose={close} />;
  if (settings && detail.data && !canManage) return <><Header settings /><Alert>{t("workspace.forbidden", { workspace: workspace?.name })}</Alert><DialogClose asChild><Button variant="ghost">{t("dialog.close")}</Button></DialogClose></>;
  if (datasets.isError && !datasets.data) return <><Header settings={settings} /><ErrorState noun={t("assistant.field.datasets")} onAction={() => void datasets.refetch()} /></>;
  if (models.data === undefined || rerankModels.data === undefined || datasets.data === undefined || settings && detail.data === undefined) return <div data-testid="assistant-skeleton" className="grid gap-4"><Header settings={settings} />{[0, 1, 2].map((n) => <Skeleton key={n} className="h-10 w-full" />)}</div>;
  return <AssistantForm key={settings ? props.assistantId : "create"} assistant={settings ? detail.data : undefined} models={models.data} rerankModels={rerankModels.data} datasets={datasets.data} pendingRef={pendingRef} onClose={close} onSaved={props.onSaved} refetchDatasets={() => datasets.refetch()} refetchModels={retryModels} />;
}
/** A fresh pending ref per opening prevents a closed request from changing the next dialog's guards. */
function OpenContent({ props }: { props: AssistantDialogProps }) {
  const pendingRef = useRef(false);
  return <DialogContent className="max-w-2xl" data-testid="assistant-dialog" onCloseAutoFocus={props.onCloseAutoFocus}
    onEscapeKeyDown={(event) => { if (pendingRef.current) event.preventDefault(); }}
    onInteractOutside={(event) => { if (pendingRef.current) event.preventDefault(); }}><Body props={props} pendingRef={pendingRef} /></DialogContent>;
}
export function AssistantDialog(props: AssistantDialogProps) {
  return <Dialog open={props.open} onOpenChange={props.onOpenChange}>{props.open ? <OpenContent key={`${props.mode}:${props.assistantId ?? "new"}`} props={props} /> : null}</Dialog>;
}
