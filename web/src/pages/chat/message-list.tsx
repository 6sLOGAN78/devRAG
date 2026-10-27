import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSessionRequest } from "@/hooks/use-chat-request";
import type { AssistantDetail, ChatMessage, Feedback, SessionDetail } from "@/services/chat-service";
import { MessageItem } from "./message-item";
import { useStickToBottom } from "./use-stick-to-bottom";

interface Props {
  assistant: AssistantDetail; sessionId?: string; session?: SessionDetail; loading?: boolean; error?: boolean; onRetry?: () => void;
  onOpenSource?: (message: ChatMessage, index: number, trigger: HTMLElement) => void; openMessageId?: string; openIndex?: number | null;
  extraMessages?: ChatMessage[]; streamingMessageId?: string; sendVersion?: number;
  onFeedback?(messageId: string, value: Feedback): Promise<void>;
}
export function MessageList({ assistant, sessionId, session, loading, error, onRetry, onOpenSource, openMessageId, openIndex, extraMessages = [], streamingMessageId, sendVersion = 0, onFeedback }: Props) {
  const { t } = useTranslation(), container = useRef<HTMLDivElement>(null);
  const [older, setOlder] = useState<ChatMessage[]>([]), [before, setBefore] = useState<string>();
  const [hasEarlier, setHasEarlier] = useState<boolean | null>(null);
  const anchor = useRef<{ id: string; top: number } | null>(null);
  const earlier = useSessionRequest(assistant.id, sessionId, before, before !== undefined);
  const messages = [...new Map([...older, ...(session?.messages ?? []), ...extraMessages].map((message) => [message.id, message])).values()];
  const stick = useStickToBottom(container, [messages.length, messages.at(-1)?.content], anchor.current !== null);
  const previousSend = useRef(sendVersion);
  useLayoutEffect(() => { if (previousSend.current !== sendVersion) { previousSend.current = sendVersion; stick.jump(); } }, [sendVersion, stick.jump]);
  useEffect(() => {
    if (before === undefined || !earlier.data || earlier.isFetching) return;
    const page = earlier.data;
    setOlder((previous) => [...new Map([...page.messages, ...previous].map((message) => [message.id, message])).values()]);
    setHasEarlier(page.hasEarlier);
  }, [before, earlier.data, earlier.isFetching]);
  useLayoutEffect(() => {
    const held = anchor.current;
    if (!held || !container.current) return;
    const element = Array.from(container.current.querySelectorAll<HTMLElement>("[data-message-id]")).find((node) => node.dataset.messageId === held.id);
    if (element) container.current.scrollTop += element.getBoundingClientRect().top - held.top;
    anchor.current = null;
  }, [older]);
  function loadEarlier() {
    const first = messages[0]; if (!first || earlier.isFetching) return;
    const element = container.current?.querySelector<HTMLElement>("[data-message-id]");
    if (element) anchor.current = { id: first.id, top: element.getBoundingClientRect().top };
    if (before === first.id) void earlier.refetch(); else setBefore(first.id);
  }
  return <div className="relative flex min-h-0 flex-1 flex-col"><div ref={container} role="log" aria-label={t("chat.message.list")} aria-live="off" tabIndex={0} onScroll={stick.onScroll} data-testid="message-list" className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
    {(hasEarlier ?? session?.hasEarlier) ? <Button variant="ghost" className="self-center" data-testid="message-load-earlier" aria-disabled={earlier.isFetching || undefined} aria-busy={earlier.isFetching || undefined} onClick={loadEarlier}>{t("chat.message.loadEarlier")}</Button> : null}
    {before !== undefined && earlier.isError ? <ErrorState heading={t("chat.error.listHeading")} onAction={() => void earlier.refetch()} /> : null}
    {assistant.promptConfig.prologue ? <p data-testid="message-greeting" className="whitespace-pre-wrap break-words text-base">{assistant.promptConfig.prologue}</p> : !sessionId ? <p data-testid="chat-draft" className="text-sm text-muted-foreground">{t("chat.draft.hint")}</p> : null}
    {loading ? <div data-testid="message-skeleton" className="grid gap-4"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div> : null}
    {error ? <ErrorState heading={t("chat.error.listHeading")} onAction={onRetry} /> : null}
    {messages.map((message) => <MessageItem key={message.id} assistant={assistant} message={message} streaming={streamingMessageId === message.id} openIndex={openMessageId === message.id ? openIndex : null} onOpenSource={onOpenSource ? (index, trigger) => onOpenSource(message, index, trigger) : undefined} onFeedback={onFeedback && /^[a-f0-9]{32}$/.test(message.id) ? (value) => onFeedback(message.id, value) : undefined} />)}
  </div>{!stick.atBottom ? <Button variant="outline" data-testid="message-jump" className="absolute bottom-2 left-1/2 -translate-x-1/2" onClick={stick.jump}><ArrowDown aria-hidden="true" />{t("chat.message.jump")}</Button> : null}</div>;
}
