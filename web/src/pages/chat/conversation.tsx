import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useChatTurn, useFeedback } from "@/hooks/use-chat-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { toReference, toUsage, type AssistantDetail, type ChatMessage, type Reference, type SessionDetail } from "@/services/chat-service";
import { SourceDrawer } from "@/components/source-drawer";
import { sourceFromReference } from "@/components/source-drawer/source-model";
import { notifyError } from "@/services/notify";
import { completionFailure } from "./errors";
import { LiveRegion } from "./live-region";
import { MessageInput } from "./message-input";
import { MessageList } from "./message-list";

interface Props {
  assistant: AssistantDetail; sessionId?: string; session?: SessionDetail; loading?: boolean; error?: boolean; onRetry?: () => void;
  onSessionId: (id: string) => void; onGone?: () => void;
  onSourceOpenChange?: (open: boolean) => void;
}
export function Conversation({ assistant, sessionId, session, loading, error, onRetry, onSessionId, onGone, onSourceOpenChange }: Props) {
  const { t } = useTranslation(), workspace = useActiveWorkspace();
  const turn = useChatTurn({ chatId: assistant.id, sessionId }), busy = turn.pending;
  const [question, setQuestion] = useState<string | null>(null), [sendError, setSendError] = useState<string | null>(null);
  const [restoreText, setRestoreText] = useState<{ text: string; nonce: number }>(), [sent, setSent] = useState(0);
  const [selectedSource, setSelectedSource] = useState<{ messageId: string; index: number; reference: Reference } | null>(null);
  const sourceTrigger = useRef<{ element: HTMLElement; kind: string } | null>(null), root = useRef<HTMLDivElement>(null);
  const feedback = useFeedback(), sourceCallback = useRef(onSourceOpenChange); sourceCallback.current = onSourceOpenChange;
  const baseline = useRef(new Set<string>()), generation = useRef(0), mounted = useRef(true);
  const currentSession = useRef(sessionId); currentSession.current = sessionId;
  const liveSession = useRef<string | undefined>(undefined), previousSession = useRef(sessionId);
  const sessionCallback = useRef(onSessionId); sessionCallback.current = onSessionId;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current += 1; }; }, []);
  useEffect(() => { setSelectedSource(null); }, [sessionId, assistant.id]);
  useEffect(() => { sourceCallback.current?.(selectedSource !== null); }, [selectedSource]);
  useEffect(() => () => { sourceCallback.current?.(false); }, []);
  useEffect(() => {
    if (previousSession.current === sessionId) return;
    previousSession.current = sessionId;
    if (sessionId !== liveSession.current) { generation.current += 1; setQuestion(null); setSendError(null); setRestoreText(undefined); }
  }, [sessionId]);
  useEffect(() => {
    const id = turn.state.sessionId;
    if (id && /^[a-f0-9]{32}$/.test(id) && currentSession.current !== id) { liveSession.current = id; sessionCallback.current(id); }
  }, [turn.state.sessionId]);
  async function send(text: string) {
    const attempt = ++generation.current;
    baseline.current = new Set(session?.messages.map((message) => message.id) ?? []);
    liveSession.current = sessionId; setQuestion(text); setSendError(null); setRestoreText(undefined); setSent((n) => n + 1);
    try { await turn.send(text); }
    catch (error) {
      if (!mounted.current || attempt !== generation.current) return;
      setQuestion(null); setRestoreText({ text, nonce: attempt });
      const failure = completionFailure(error);
      if (failure.kind === "gone") onGone?.();
      else if (failure.kind === "toast") notifyError({ title: t(failure.key, { workspace: workspace?.name }), description: "", id: `chat-send-${assistant.id}` });
      else setSendError(t(failure.key));
    }
  }
  const stored = session?.messages ?? [];
  const ended = ["finished", "stopped", "failed"].includes(turn.state.status);
  const reconciled = ended && stored.some((message) => message.role === "assistant" && (turn.state.messageId ? message.id === turn.state.messageId : !baseline.current.has(message.id)));
  const extra: ChatMessage[] = [];
  if (question !== null && turn.state.status !== "idle" && !reconciled) {
    if (!stored.some((message) => message.role === "user" && !baseline.current.has(message.id) && message.content === question)) extra.push({ id: "local-user", role: "user", content: question, createdAt: 0, finish: "complete", reference: { chunks: [], docAggs: [] }, usage: null, latencyMs: null, empty: false, feedback: null });
    extra.push({ id: turn.state.messageId || "local-assistant", role: "assistant", content: turn.state.text, createdAt: 0,
      finish: turn.state.status === "failed" ? "failed" : turn.state.status === "stopped" ? "stopped" : "complete", reference: toReference(turn.state.reference), usage: turn.state.usage === null ? null : toUsage(turn.state.usage), latencyMs: turn.state.latencyMs, empty: turn.state.empty, feedback: null });
  }
  const currentReference = selectedSource ? [...stored, ...extra].find((message) => message.id === selectedSource.messageId)?.reference ?? selectedSource.reference : null;
  const source = selectedSource && currentReference ? sourceFromReference(currentReference, selectedSource.index) : null;
  useEffect(() => { if (selectedSource && !source) setSelectedSource(null); }, [selectedSource, source]);
  return <div ref={root} className="flex min-h-0 flex-1 flex-col">
    <MessageList key={`${assistant.id}:${sessionId ?? "draft"}`} assistant={assistant} sessionId={sessionId} session={session} loading={loading} error={error} onRetry={onRetry} extraMessages={extra} streamingMessageId={turn.state.status === "streaming" ? turn.state.messageId || "local-assistant" : undefined} sendVersion={sent}
      openMessageId={selectedSource?.messageId} openIndex={selectedSource?.index} onOpenSource={(message, index, trigger) => {
        if (!sourceFromReference(message.reference, index)) return;
        sourceTrigger.current = { element: trigger, kind: trigger.dataset.testid === "source-chip" ? "source-chip" : "cite-pill" };
        setSelectedSource({ messageId: message.id, index, reference: message.reference });
      }} onFeedback={sessionId ? async (messageId, thumb) => { await feedback.mutateAsync({ chatId: assistant.id, sessionId, messageId, thumb }); } : undefined} />
    <MessageInput busy={busy} disabled={loading} error={sendError} restoreText={restoreText} onSend={send} onStop={turn.stop} />
    <LiveRegion state={turn.state} />
    <SourceDrawer source={source} open={selectedSource !== null && source !== null} onOpenChange={(open) => { if (!open) setSelectedSource(null); }} onCloseAutoFocus={(event) => {
      event.preventDefault(); const trigger = sourceTrigger.current;
      if (trigger?.element.isConnected) trigger.element.focus();
      else if (trigger && selectedSource) root.current?.querySelector<HTMLElement>(`[data-message-id="${selectedSource.messageId}"] [data-testid="${trigger.kind}"][data-cite-index="${selectedSource.index}"]`)?.focus();
    }} />
  </div>;
}
