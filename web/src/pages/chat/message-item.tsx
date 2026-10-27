import { CircleAlert, CircleSlash, Loader2, SearchX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AvatarInitials } from "@/components/avatar-initials";
import { MessageMarkdown } from "@/components/markdown-content";
import { Badge } from "@/components/ui/badge";
import type { AssistantDetail, ChatMessage, Feedback } from "@/services/chat-service";
import { FeedbackButtons } from "./feedback-buttons";
import { SourceChips } from "./source-chips";

export interface MessageItemProps {
  assistant: AssistantDetail; message: ChatMessage; streaming?: boolean; openIndex?: number | null; onOpenSource?: (index: number, trigger: HTMLElement) => void;
  onFeedback?(value: Feedback): Promise<void>;
}
const ignoreSource = () => {};
const USAGE_COPY = { estimated: "chat.message.tokensApprox", measured: "chat.message.tokens" };
export function MessageItem({ assistant, message, streaming = false, openIndex, onOpenSource = ignoreSource, onFeedback }: MessageItemProps) {
  const { t } = useTranslation();
  const tokensKey = USAGE_COPY[message.usage?.estimated ? "estimated" : "measured"];
  if (message.role === "user") return <article aria-label={t("chat.message.you")} data-testid="message-user" data-message-id={message.id} className="ml-auto max-w-xl whitespace-pre-wrap break-words rounded-lg bg-muted px-4 py-2 text-base">{message.content}</article>;
  const showMeta = !streaming && message.finish !== "failed" && !(message.finish === "stopped" && !message.content);
  return <article aria-label={assistant.name} aria-busy={streaming || undefined} data-testid="message-assistant" data-message-id={message.id} data-finish={message.finish} className="flex min-w-0 items-start gap-2">
    <AvatarInitials avatar={assistant.icon} nickname={assistant.name} email="" />
    <div className="grid min-w-0 flex-1 gap-2">
      {message.content ? <MessageMarkdown text={message.content} streaming={streaming} chunks={streaming ? null : message.reference.chunks} openIndex={openIndex} onOpenSource={onOpenSource} /> : streaming ? <p data-testid="message-generating" className="inline-flex items-center gap-1 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />{t(assistant.kbIds.length ? "chat.message.generating" : "chat.message.thinking")}</p> : null}
      {streaming ? null : message.finish === "stopped" ? <div data-testid="message-stopped" className="grid gap-1"><Badge variant="outline" className="w-fit"><CircleSlash className="mr-1 size-3" aria-hidden="true" />{t("chat.message.stopped")}</Badge><p className="text-xs text-muted-foreground">{t("chat.message.stoppedNote")}</p></div>
        : message.finish === "failed" ? <p data-testid="message-failed" className="inline-flex items-center gap-1 text-sm text-destructive"><CircleAlert className="size-4 shrink-0" aria-hidden="true" />{t("chat.message.failed")}</p>
        : message.empty ? <Badge variant="outline" className="w-fit" data-testid="message-empty-badge"><SearchX className="mr-1 size-3" aria-hidden="true" />{t("chat.message.noSources")}</Badge> : null}
      {!streaming && message.finish !== "failed" ? <SourceChips chunks={message.reference.chunks} onOpen={onOpenSource} openIndex={openIndex} /> : null}
      {showMeta && (message.latencyMs !== null || message.usage !== null) ? <p data-testid="message-meta" className="text-xs font-normal tabular-nums text-muted-foreground">
        {message.latencyMs !== null ? <span data-testid="message-latency">{t("chat.message.latency", { seconds: (message.latencyMs / 1000).toFixed(1) })}</span> : null}
        {message.latencyMs !== null && message.usage !== null ? <span aria-hidden="true"> · </span> : null}
        {message.usage !== null ? <span data-testid="message-tokens">{t(tokensKey, { count: message.usage.total })}</span> : null}
      </p> : null}
      {!streaming && message.finish === "complete" && !message.empty && onFeedback ? <FeedbackButtons messageId={message.id} value={message.feedback} onChange={onFeedback} /> : null}
    </div>
  </article>;
}
