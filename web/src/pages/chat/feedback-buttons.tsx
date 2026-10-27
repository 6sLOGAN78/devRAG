import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { Feedback } from "@/services/chat-service";
import { notifyError } from "@/services/notify";

export function FeedbackButtons({ messageId, value, onChange }: { messageId: string; value: Feedback; onChange(value: Feedback): Promise<void> }) {
  const { t } = useTranslation(), pending = useRef(false), mounted = useRef(true), [busy, setBusy] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function rate(next: Exclude<Feedback, null>) {
    if (pending.current) return;
    pending.current = true; setBusy(true);
    try { await onChange(value === next ? null : next); }
    catch { if (mounted.current) notifyError({ title: t("chat.message.feedbackFailed"), description: "", id: `feedback-${messageId}` }); }
    finally { pending.current = false; if (mounted.current) setBusy(false); }
  }
  return <div className="flex items-center gap-1">{(["up", "down"] as const).map((rating) => <Button key={rating} type="button" variant="ghost" size="icon" data-testid={`feedback-${rating}`} aria-label={t(rating === "up" ? "chat.message.feedbackUp" : "chat.message.feedbackDown")} aria-pressed={value === rating} aria-busy={busy || undefined} aria-disabled={busy || undefined} onClick={() => void rate(rating)}>
    {rating === "up" ? <ThumbsUp aria-hidden="true" /> : <ThumbsDown aria-hidden="true" />}
  </Button>)}</div>;
}
