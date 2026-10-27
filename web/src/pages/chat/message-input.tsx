import { Send, Square } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface Props {
  busy: boolean; disabled?: boolean; error?: string | null; restoreText?: string | { text: string; nonce: number };
  onSend(text: string): void | Promise<void>; onStop: () => void;
}
export function MessageInput({ busy, disabled = false, error, restoreText, onSend, onStop }: Props) {
  const { t } = useTranslation(), id = useId();
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null), composing = useRef(false), inFlight = useRef(false), mounted = useRef(true);
  const focusInput = () => { if (!document.activeElement?.closest('[role="dialog"], [role="alertdialog"]')) input.current?.focus(); };
  const tooLong = text.length > 8000, allowed = !busy && !disabled && !tooLong && text.trim() !== "";
  useEffect(() => { mounted.current = true; focusInput(); return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (!busy) focusInput(); }, [busy]);
  useEffect(() => { if (restoreText !== undefined) { setText(typeof restoreText === "string" ? restoreText : restoreText.text); focusInput(); } }, [restoreText]);
  useEffect(() => { const element = input.current; if (element) { element.style.height = "0px"; element.style.height = `${Math.max(40, Math.min(160, element.scrollHeight))}px`; } }, [text]);
  async function send() {
    if (inFlight.current || !allowed) return;
    const question = text; inFlight.current = true; setText("");
    try { await onSend(question); }
    catch { if (mounted.current) setText(question); }
    finally { inFlight.current = false; if (mounted.current) focusInput(); }
  }
  const actionLabel = t(busy ? "chat.input.stopLabel" : "chat.input.sendLabel");
  return <div className="grid gap-2 border-t p-4">
    {error ? <Alert data-testid="chat-send-error">{error}</Alert> : null}
    <Label htmlFor={id} className="sr-only">{t("chat.input.label")}</Label>
    <div className="flex items-end gap-2"><Textarea ref={input} id={id} data-testid="chat-input" value={text} rows={1} readOnly={busy || disabled} aria-busy={busy || undefined} aria-invalid={tooLong || undefined}
      aria-describedby={`${id}-hint${tooLong ? ` ${id}-error` : ""}`} placeholder={t("chat.input.placeholder")} className="min-h-10 max-h-40 resize-none overflow-y-auto"
      onChange={(event) => setText(event.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && busy) { event.preventDefault(); onStop(); }
        if (event.key === "Enter" && !event.shiftKey && !composing.current && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); void send(); }
      }} />
      <TooltipProvider><Tooltip><TooltipTrigger asChild><Button type="button" variant={busy ? "outline" : "default"} data-testid={busy ? "chat-stop" : "chat-send"} aria-label={actionLabel} aria-disabled={!busy && !allowed || undefined}
        className="aria-disabled:opacity-50" onClick={() => { if (busy) onStop(); else void send(); }}>{busy ? <Square aria-hidden="true" /> : <Send aria-hidden="true" />}{t(busy ? "chat.input.stop" : "chat.input.send")}</Button></TooltipTrigger><TooltipContent>{actionLabel}</TooltipContent></Tooltip></TooltipProvider>
    </div>
    <div className="flex justify-between gap-2"><p id={`${id}-hint`} data-testid="chat-hint" className="text-xs text-muted-foreground">{t("chat.input.hint")}</p>{text.length >= 7000 ? <p data-testid="chat-counter" aria-live="polite" className="text-xs tabular-nums text-muted-foreground">{t("chat.input.counter", { used: text.length, max: 8000 })}</p> : null}</div>
    {tooLong ? <p id={`${id}-error`} role="alert" className="text-xs text-destructive">{t("chat.input.tooLong")}</p> : null}
  </div>;
}
