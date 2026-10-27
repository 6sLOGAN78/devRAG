import { useQueryClient } from "@tanstack/react-query";
import { PanelLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { assistantsKey, useAssistantRequest, useAssistantsRequest, useSessionRequest } from "@/hooks/use-chat-request";
import { notifySuccess } from "@/services/notify";
import { AssistantDialog } from "./assistant-dialog";
import { AssistantRail } from "./assistant-rail";
import { ConversationHeader } from "./conversation-header";
import { Conversation } from "./conversation";
import { DeleteAssistantDialog, DeleteChatDialog } from "./delete-dialogs";
import { pageFailure } from "./errors";
import { ConversationSkeleton, NoAssistants } from "./page-states";
import { useChatParams } from "./use-chat-params";

function useWideScreen() {
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  useEffect(() => { const query = window.matchMedia("(min-width: 1024px)"); const update = () => setWide(query.matches); update(); query.addEventListener("change", update); return () => query.removeEventListener("change", update); }, []);
  return wide;
}
export default function ChatPage() {
  const { t, i18n } = useTranslation(), params = useChatParams(), client = useQueryClient(), wide = useWideScreen();
  const [page, setPage] = useState(1), [keywords, setKeywords] = useState(""), [chatPage, setChatPage] = useState(1);
  const [creating, setCreating] = useState(false), [railOpen, setRailOpen] = useState(false);
  const [editing, setEditing] = useState(false), [deleting, setDeleting] = useState<"chat" | "assistant" | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const trigger = useRef<HTMLElement | null>(null), root = useRef<HTMLDivElement>(null);
  const createAfterRail = useRef<HTMLElement | null>(null);
  const previousTenant = useRef(params.tenantId), gone = useRef(new Set<string>());
  const assistants = useAssistantsRequest(page, keywords, params.bound);
  const assistant = useAssistantRequest(params.chatId ?? undefined, params.bound && deleting !== "assistant");
  const session = useSessionRequest(params.chatId ?? undefined, params.sessionId ?? undefined, undefined, params.bound && assistant.isSuccess && deleting !== "chat");
  useEffect(() => { document.title = t("chat.documentTitle"); }, [t, i18n.language]);
  useEffect(() => {
    if (previousTenant.current === params.tenantId) return;
    previousTenant.current = params.tenantId; gone.current.clear(); createAfterRail.current = null; setPage(1); setKeywords(""); setChatPage(1); setCreating(false); setEditing(false); setDeleting(null); setRailOpen(false);
  }, [params.tenantId]);
  useEffect(() => { setChatPage(1); setEditing(false); setDeleting(null); setSourceOpen(false); }, [params.chatId]);
  useEffect(() => {
    const pages = Math.max(1, Math.ceil((assistants.data?.total ?? 0) / 20));
    if (assistants.data && !assistants.isPlaceholderData && page > pages) setPage(pages);
  }, [assistants.data, assistants.isPlaceholderData, page]);
  useEffect(() => {
    if (!params.bound || params.chatId || assistants.isPlaceholderData || assistants.isError) return;
    const first = assistants.data?.items.find((item) => !gone.current.has(item.id));
    if (first) params.select(first.id, true);
  }, [params, assistants.data, assistants.isPlaceholderData, assistants.isError]);
  useEffect(() => {
    if (deleting !== null || editing) return;
    if (params.chatId && assistant.isError && pageFailure(assistant.error) === "gone") {
      const id = params.chatId; gone.current.add(id);
      client.setQueryData(assistantsKey(params.tenantId, page, keywords), (data: { items: { id: string }[]; total: number } | undefined) => data ? { ...data, items: data.items.filter((item) => item.id !== id), total: Math.max(0, data.total - (data.items.some((item) => item.id === id) ? 1 : 0)) } : data);
      notifySuccess(t("chat.gone.assistant")); params.clear();
    } else if (params.sessionId && session.isError && pageFailure(session.error) === "gone") {
      notifySuccess(t("chat.gone.chat")); params.newChat(true);
    }
  }, [assistant.isError, assistant.error, session.isError, session.error, params, client, page, keywords, t, deleting, editing]);
  function create(opener: HTMLElement) {
    trigger.current = opener;
    if (railOpen) { createAfterRail.current = opener; setRailOpen(false); }
    else setCreating(true);
  }
  function restoreFocus(event: Event) {
    event.preventDefault();
    (trigger.current?.isConnected ? trigger.current : root.current?.querySelector<HTMLElement>('[data-testid="rail-assistant-new"], [data-testid="rail-open"]'))?.focus();
  }
  function removeAssistantSelection() {
    if (params.chatId) gone.current.add(params.chatId);
    params.clear();
  }
  const hasHeader = assistant.data !== undefined && (!assistant.isError || deleting !== null || editing);
  const rail = <AssistantRail assistants={assistants} chatId={params.chatId} sessionId={params.sessionId} keywords={keywords} page={page} chatPage={chatPage} onPage={setPage} onChatPage={setChatPage}
    onSearch={(value) => { setPage(1); setKeywords(value); }} onSelect={(id) => { params.select(id); setRailOpen(false); }} onSession={(id) => { params.selectSession(id); setRailOpen(false); }} onNewChat={() => { params.newChat(); setRailOpen(false); }} onCreate={create} />;
  let content;
  if (!params.bound || assistants.isPending && !params.chatId) content = <ConversationSkeleton />;
  else if (!params.chatId && assistants.data?.total === 0 && !keywords) content = <NoAssistants onCreate={create} />;
  else if (assistant.isError && deleting === null && !editing) content = <div data-testid={pageFailure(assistant.error) === "gone" ? "chat-not-found" : undefined}><ErrorState heading={t("chat.error.pageHeading")} onAction={() => void assistant.refetch()} /></div>;
  else if (params.chatId && !assistant.data) content = <ConversationSkeleton />;
  else if (assistant.data) content = <>
    <ConversationHeader assistant={assistant.data} session={session.data} onOpenRail={!wide ? () => setRailOpen(true) : undefined}
      onSettings={(opener) => { if (!sourceOpen && !railOpen && !creating && deleting === null) { trigger.current = opener; setEditing(true); } }}
      onDeleteChat={(opener) => { if (!sourceOpen && !railOpen && !creating && !editing) { trigger.current = opener; setDeleting("chat"); } }}
      onDeleteAssistant={(opener) => { if (!sourceOpen && !railOpen && !creating && !editing) { trigger.current = opener; setDeleting("assistant"); } }} />
    <Conversation key={assistant.data.id} assistant={assistant.data} sessionId={params.sessionId ?? undefined} session={session.data}
      loading={params.sessionId !== null && session.isPending} error={params.sessionId !== null && session.isError} onRetry={() => void session.refetch()}
      onSourceOpenChange={setSourceOpen} onSessionId={(id) => params.selectSession(id, true)} onGone={() => { if (params.sessionId) { notifySuccess(t("chat.gone.chat")); params.newChat(true); } else { notifySuccess(t("chat.gone.assistant")); params.clear(); } }} />
  </>;
  return <div ref={root} data-testid="chat-page" className="flex h-[calc(100dvh-8rem)] min-h-[480px] gap-6">
    {wide ? rail : <Sheet open={railOpen} onOpenChange={setRailOpen}>{!hasHeader ? <SheetTrigger asChild><Button data-testid="rail-open" variant="ghost" size="icon" className="shrink-0 self-start" aria-label={t("chat.rail.open")}><PanelLeft aria-hidden="true" /></Button></SheetTrigger> : null}
      <SheetContent side="left" className="w-80" aria-describedby={undefined} onCloseAutoFocus={(event) => {
        if (createAfterRail.current) { event.preventDefault(); createAfterRail.current = null; setCreating(true); }
        else { event.preventDefault(); root.current?.querySelector<HTMLElement>('[data-testid="rail-open"]')?.focus(); }
      }}><SheetTitle className="sr-only">{t("chat.rail.open")}</SheetTitle>{rail}</SheetContent></Sheet>}
    <section className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label={t("chat.documentTitle")}>{content}</section>
    <AssistantDialog open={creating || editing} mode={creating ? "create" : "settings"} assistantId={params.chatId ?? undefined} onOpenChange={(open) => { if (!open) { setCreating(false); setEditing(false); } }} onCloseAutoFocus={restoreFocus}
      onSaved={({ id, created, leftList }) => { if (leftList) removeAssistantSelection(); else if (created) params.select(id); }} />
    {assistant.data ? <DeleteAssistantDialog assistant={assistant.data} open={deleting === "assistant"} onOpenChange={(open) => { if (!open) setDeleting(null); }} onDeleted={removeAssistantSelection} onCloseAutoFocus={restoreFocus} /> : null}
    {session.data && params.chatId ? <DeleteChatDialog chatId={params.chatId} session={session.data} open={deleting === "chat"} onOpenChange={(open) => { if (!open) setDeleting(null); }} onDeleted={() => params.newChat(true)} onCloseAutoFocus={restoreFocus} /> : null}
  </div>;
}
