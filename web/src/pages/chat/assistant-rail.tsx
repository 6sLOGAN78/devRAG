import type { UseQueryResult } from "@tanstack/react-query";
import { Lock, Plus, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AvatarInitials } from "@/components/avatar-initials";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { cn } from "@/lib/utils";
import type { AssistantView } from "@/services/chat-service";
import { ChatList, RailSkeleton } from "./chat-list";

export function AssistantRail({ assistants, chatId, sessionId, keywords, page, chatPage, onSearch, onPage, onChatPage, onSelect, onSession, onNewChat, onCreate }: {
  assistants: UseQueryResult<{ items: AssistantView[]; total: number }, Error>;
  chatId: string | null; sessionId: string | null; keywords: string; page: number; chatPage: number;
  onSearch: (value: string) => void; onPage: (page: number) => void; onChatPage: (page: number) => void;
  onSelect: (id: string) => void; onSession: (id: string) => void; onNewChat: () => void; onCreate: (trigger: HTMLElement) => void;
}) {
  const { t } = useTranslation(), pages = Math.max(1, Math.ceil((assistants.data?.total ?? 0) / 20));
  return <aside data-testid="chat-rail" className="flex h-full min-h-0 w-72 shrink-0 flex-col gap-4 overflow-y-auto pr-1">
    <div className="flex items-center justify-between gap-2"><h2 className="text-xs font-semibold">{t("chat.rail.assistants")}</h2>
      <Button size="sm" variant="outline" data-testid="rail-assistant-new" onClick={(event) => onCreate(event.currentTarget)}><Plus aria-hidden="true" />{t("chat.rail.newAssistant")}</Button></div>
    <div data-testid="rail-assistant-search"><SearchInput value={keywords} onSearch={(value) => onSearch(value.slice(0, 128))} label={t("chat.rail.search")} clearLabel={t("common.search.clear")} /></div>
    <div className="grid gap-1">
      {assistants.isPending ? <RailSkeleton /> : assistants.isError ? <ErrorState heading={t("chat.rail.assistantsError")} onAction={() => void assistants.refetch()} /> : keywords && !assistants.data?.items.length ? <p className="text-sm text-muted-foreground">{t("chat.rail.noMatch")}</p> : null}
      {assistants.data?.items.map((assistant) => <button key={assistant.id} type="button" data-testid="rail-assistant-row" data-chat-id={assistant.id} aria-current={chatId === assistant.id ? "true" : undefined} onClick={() => onSelect(assistant.id)}
        className={cn("relative flex min-h-10 items-center gap-2 rounded p-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", chatId === assistant.id && "bg-muted before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-primary")}>
        <AvatarInitials avatar="" nickname={assistant.name} email="" size="md" />
        <span className="grid min-w-0 gap-1"><span className="truncate text-sm font-semibold" title={assistant.name}>{assistant.name}</span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">{assistant.permission === "team" ? <Users className="size-3" aria-hidden="true" /> : <Lock className="size-3" aria-hidden="true" />}{t(assistant.permission === "team" ? "assistant.visibility.team" : "assistant.visibility.me")}</span></span>
      </button>)}
    </div>
    <Pagination data-testid="rail-assistant-pages" aria-label={t("chat.rail.assistantPages")} page={page} pages={pages} onPageChange={onPage} previousLabel={t("common.pagination.previous")} nextLabel={t("common.pagination.next")} statusLabel={t("common.pagination.status", { page, pages })} />
    {chatId ? <ChatList key={chatId} chatId={chatId} sessionId={sessionId} page={chatPage} onPage={onChatPage} onSelect={onSession} onNew={onNewChat} /> : null}
  </aside>;
}
