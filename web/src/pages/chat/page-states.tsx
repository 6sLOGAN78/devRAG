import { MessagesSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
export function NoAssistants({ onCreate }: { onCreate: (trigger: HTMLElement) => void }) {
  const { t } = useTranslation();
  return <EmptyState as="h2" icon={MessagesSquare} heading={t("chat.empty.heading")} body={t("chat.empty.body")} action={<Button data-testid="chat-empty-create" onClick={(event) => onCreate(event.currentTarget)}>{t("chat.empty.action")}</Button>} />;
}
export function ConversationSkeleton() {
  return <div data-testid="chat-skeleton" className="grid gap-4 p-4"><Skeleton className="h-10 w-48" /><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>;
}
