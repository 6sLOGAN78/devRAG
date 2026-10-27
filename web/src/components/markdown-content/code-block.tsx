import { Check, Copy } from "lucide-react";
import { Children, isValidElement, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { notifyError, notifySuccess } from "@/services/notify";

function codeText(children: ReactNode): string {
  return Children.toArray(children).map((child) => {
    if (typeof child === "string" || typeof child === "number") return String(child);
    return isValidElement<{ children?: ReactNode }>(child) ? codeText(child.props.children) : "";
  }).join("");
}
export function CodeBlock({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const mounted = useRef(true), timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; clearTimeout(timer.current); }; }, []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codeText(children));
      if (!mounted.current) return;
      setCopied(true); clearTimeout(timer.current); timer.current = setTimeout(() => setCopied(false), 2000);
      notifySuccess(t("chat.code.copied"));
    } catch {
      if (mounted.current) notifyError({ id: "chat-code-copy", title: t("chat.code.copyFailed"), description: "" });
    }
  };
  return <div className="relative my-2 min-w-0">
    <pre tabIndex={0} className="max-h-96 overflow-x-auto rounded-md border bg-background p-4 pr-14 font-mono text-sm [&_code]:bg-transparent [&_code]:p-0">{children}</pre>
    <Button type="button" variant="ghost" size="icon" className="absolute right-1 top-1" data-testid="code-copy" data-copied={copied}
      aria-label={t("chat.code.copy")} onClick={() => void copy()}>{copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}</Button>
  </div>;
}
