import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { useAssistantRequest, useDeleteAssistant, useDeleteSession } from "@/hooks/use-chat-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { AssistantDetail, SessionView } from "@/services/chat-service";
import { ApiError } from "@/services/http";
import { notifyError, notifySuccess } from "@/services/notify";

interface DialogProps { open: boolean; onOpenChange: (open: boolean) => void; onDeleted: () => void; onCloseAutoFocus?: (event: Event) => void }
interface AssistantProps extends DialogProps { assistant: AssistantDetail }
interface ChatProps extends DialogProps { chatId: string; session: SessionView }
function DeleteBody({ kind, assistant, session, chatId, onOpenChange, onDeleted, onCloseAutoFocus }: {
  kind: "assistant" | "chat"; assistant?: AssistantDetail; session?: SessionView; chatId: string;
} & Omit<DialogProps, "open">) {
  const { t } = useTranslation(), workspace = useActiveWorkspace();
  const { refetch } = useAssistantRequest(chatId, false);
  const removeAssistant = useDeleteAssistant(), removeChat = useDeleteSession();
  const [count, setCount] = useState(assistant?.membersWithChats ?? 0), [fresh, setFresh] = useState(kind === "chat"), [busy, setBusy] = useState(false);
  const inFlight = useRef(false), mounted = useRef(true), completed = useRef(false);
  const callbacks = useRef({ onDeleted, onOpenChange }); callbacks.current = { onDeleted, onOpenChange };
  useEffect(() => {
    mounted.current = true;
    if (kind === "assistant") void refetch().then((result) => {
      if (!mounted.current || completed.current) return;
      if (result.error instanceof ApiError && result.error.status === 404) {
        completed.current = true; callbacks.current.onOpenChange(false); callbacks.current.onDeleted(); return;
      }
      if (result.data) setCount(result.data.membersWithChats);
      setFresh(true);
    });
    return () => { mounted.current = false; };
  }, [chatId, kind, refetch]);
  const prefix = kind === "assistant" ? "assistant.delete" : "assistant.deleteChat";
  async function confirm() {
    if (inFlight.current || !fresh) return;
    inFlight.current = true; setBusy(true);
    try {
      if (kind === "assistant") await removeAssistant.mutateAsync(chatId);
      else await removeChat.mutateAsync({ chatId, sessionId: session!.id });
      if (!mounted.current) return;
      completed.current = true; notifySuccess(t(`${prefix}.done`)); onOpenChange(false); onDeleted();
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiError && error.status === 404) { completed.current = true; onOpenChange(false); onDeleted(); }
      else notifyError({ title: t(error instanceof ApiError && error.status === 403 ? "workspace.forbidden" : `${prefix}.failed`, { workspace: workspace?.name }), description: "", id: `delete-${kind}-${chatId}` });
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  return <AlertDialogContent data-testid={`delete-${kind}-dialog`} onCloseAutoFocus={onCloseAutoFocus} onEscapeKeyDown={(event) => { if (inFlight.current) event.preventDefault(); }}>
    <AlertDialogHeader><AlertDialogTitle>{t(`${prefix}.title`)}</AlertDialogTitle>
      <AlertDialogDescription data-testid={kind === "assistant" ? "delete-assistant-body" : undefined} data-count={kind === "assistant" ? count : undefined}>
        {t(kind === "assistant" && assistant?.permission === "team" && count > 0 ? "assistant.delete.bodyTeam" : `${prefix}.body`, { name: assistant?.name ?? session?.name ?? t("chat.rail.untitled"), count })}
      </AlertDialogDescription></AlertDialogHeader>
    <AlertDialogFooter><AlertDialogCancel data-testid={`delete-${kind}-keep`} onClick={(event) => { if (inFlight.current) event.preventDefault(); }}>{t(`${prefix}.keep`)}</AlertDialogCancel>
      <AlertDialogAction variant="destructive" data-testid={`delete-${kind}-confirm`} aria-disabled={!fresh || busy || undefined} aria-busy={!fresh || busy || undefined} className="aria-disabled:pointer-events-none aria-disabled:opacity-50" onClick={(event) => { event.preventDefault(); void confirm(); }}>{t(`${prefix}.confirm`)}</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>;
}
export function DeleteAssistantDialog(props: AssistantProps) {
  return <AlertDialog open={props.open} onOpenChange={props.onOpenChange}>{props.open ? <DeleteBody key={props.assistant.id} kind="assistant" chatId={props.assistant.id} {...props} /> : null}</AlertDialog>;
}
export function DeleteChatDialog(props: ChatProps) {
  return <AlertDialog open={props.open} onOpenChange={props.onOpenChange}>{props.open ? <DeleteBody key={props.session.id} kind="chat" {...props} /> : null}</AlertDialog>;
}
