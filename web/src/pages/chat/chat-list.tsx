import { MessageSquarePlus } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useSessionsRequest } from "@/hooks/use-chat-request";
import { cn } from "@/lib/utils";

export function ChatList({ chatId, sessionId, page, onPage, onSelect, onNew }: {
  chatId: string; sessionId: string | null; page: number; onPage: (page: number) => void; onSelect: (id: string) => void; onNew: () => void;
}) {
  const { t, i18n } = useTranslation(), sessions = useSessionsRequest(chatId, page);
  const pages = Math.max(1, Math.ceil((sessions.data?.total ?? 0) / 20));
  useEffect(() => { if (sessions.data && !sessions.isPlaceholderData && page > pages) onPage(pages); }, [sessions.data, sessions.isPlaceholderData, page, pages, onPage]);
  return <section className="grid gap-2 border-t pt-4">
    <div className="flex items-center justify-between gap-2"><h2 className="text-xs font-semibold">{t("chat.rail.chats")}</h2>
      <Button size="sm" variant="outline" onClick={onNew} data-testid="rail-chat-new"><MessageSquarePlus aria-hidden="true" />{t("chat.rail.newChat")}</Button></div>
    {sessions.isPending ? <RailSkeleton /> : sessions.isError ? <ErrorState heading={t("chat.rail.chatsError")} onAction={() => void sessions.refetch()} /> : !sessions.data?.items.length ? <p className="text-sm text-muted-foreground">{t("chat.rail.noChats")}</p> : null}
    {sessions.data?.items.map((session) => <button key={session.id} type="button" data-testid="rail-chat-row" data-session-id={session.id} aria-current={sessionId === session.id ? "true" : undefined} onClick={() => onSelect(session.id)}
      className={cn("relative grid min-h-10 gap-1 rounded p-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", sessionId === session.id && "bg-muted before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-primary")}>
      <span className="truncate text-sm" title={session.name}>{session.name || t("chat.rail.untitled")}</span>
      <time className="text-xs text-muted-foreground" dateTime={new Date(session.updateTime).toISOString()}>{new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(session.updateTime)}</time>
    </button>)}
    <Pagination data-testid="rail-chat-pages" aria-label={t("chat.rail.chatPages")} page={page} pages={pages} onPageChange={onPage} previousLabel={t("common.pagination.previous")} nextLabel={t("common.pagination.next")} statusLabel={t("common.pagination.status", { page, pages })} />
  </section>;
}
export function RailSkeleton() {
  return <div data-testid="rail-skeleton" className="grid gap-2">{[0, 1, 2, 3, 4].map((index) => <Skeleton key={index} className="h-10 w-full" />)}</div>;
}
