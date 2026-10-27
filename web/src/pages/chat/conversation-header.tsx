import { EllipsisVertical, Lock, PanelLeft, Settings2, Trash2, Users } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { AvatarInitials } from "@/components/avatar-initials";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAssistantPermissions } from "@/hooks/use-assistant-permissions";
import type { AssistantDetail, SessionView } from "@/services/chat-service";

export function ConversationHeader({ assistant, session, onSettings, onDeleteChat, onDeleteAssistant, onOpenRail }: {
  assistant: AssistantDetail; session?: SessionView; onSettings: (trigger: HTMLElement) => void;
  onDeleteChat: (trigger: HTMLElement) => void; onDeleteAssistant: (trigger: HTMLElement) => void; onOpenRail?: () => void;
}) {
  const { t } = useTranslation(), canManage = useAssistantPermissions(assistant);
  const menuTrigger = useRef<HTMLButtonElement>(null), chosen = useRef<"chat" | "assistant" | null>(null);
  return <header className="grid gap-3 border-b p-4" data-testid="chat-header">
    <div className="flex items-center gap-2">
      {onOpenRail ? <Button size="icon" variant="ghost" data-testid="rail-open" aria-label={t("chat.rail.open")} onClick={onOpenRail}><PanelLeft aria-hidden="true" /></Button> : null}
      <AvatarInitials avatar={assistant.icon} nickname={assistant.name} email="" size="md" />
      <div className="min-w-0 flex-1"><h1 className="truncate text-xl font-semibold" title={assistant.name}>{assistant.name}</h1>{session ? <p className="truncate text-xs text-muted-foreground">{session.name || t("chat.rail.untitled")}</p> : null}</div>
      <Badge variant="outline" data-testid="chat-visibility">{assistant.permission === "team" ? <Users className="mr-1 size-3" aria-hidden="true" /> : <Lock className="mr-1 size-3" aria-hidden="true" />}{t(assistant.permission === "team" ? "assistant.visibility.team" : "assistant.visibility.me")}</Badge>
      {canManage ? <Button variant="outline" data-testid="chat-settings" onClick={(event) => onSettings(event.currentTarget)}><Settings2 aria-hidden="true" />{t("chat.header.settings")}</Button> : null}
      {canManage || session ? <DropdownMenu modal={false}><DropdownMenuTrigger asChild><Button ref={menuTrigger} variant="ghost" size="icon" data-testid="chat-more" aria-label={t("chat.header.more", { name: assistant.name })}><EllipsisVertical aria-hidden="true" /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" onCloseAutoFocus={(event) => {
          const action = chosen.current; chosen.current = null;
          if (action && menuTrigger.current) { event.preventDefault(); (action === "chat" ? onDeleteChat : onDeleteAssistant)(menuTrigger.current); }
        }}>
          {session ? <DropdownMenuItem data-testid="chat-menu-delete-chat" className="text-destructive focus:text-destructive" onSelect={() => { chosen.current = "chat"; }}><Trash2 aria-hidden="true" />{t("chat.header.deleteChat")}</DropdownMenuItem> : null}
          {canManage ? <DropdownMenuItem data-testid="chat-menu-delete-assistant" className="text-destructive focus:text-destructive" onSelect={() => { chosen.current = "assistant"; }}><Trash2 aria-hidden="true" />{t("chat.header.deleteAssistant")}</DropdownMenuItem> : null}
        </DropdownMenuContent></DropdownMenu> : null}
    </div>
    {assistant.unavailableDatasets > 0 ? <Alert variant="info" data-testid="chat-datasets-notice">{assistant.kbIds.length ? t("chat.notice.skipped", { count: assistant.unavailableDatasets }) : t("chat.notice.noneAvailable")}</Alert> : null}
  </header>;
}
