import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

const resourceId = (value: string | null) => value !== null && /^[0-9a-f]{32}$/.test(value) ? value : null;
export function useChatParams() {
  const [params, setParams] = useSearchParams();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const userId = useUserStore((state) => state.user?.id);
  const initialized = useWorkspaceStore((state) => state.initialisedFor === userId && state.activeTenantId === tenantId);
  // A restored membership may arrive after the own-workspace fallback. Bind once before treating a change as a switch.
  const previousTenant = useRef(initialized ? tenantId : null);
  const clearing = useRef(false);
  if (clearing.current && !params.has("chat") && !params.has("session")) clearing.current = false;
  const changing = previousTenant.current !== null && previousTenant.current !== tenantId;
  const bound = initialized && tenantId !== null && !changing && !clearing.current;
  const chatId = bound ? resourceId(params.get("chat")) : null;
  const sessionId = chatId ? resourceId(params.get("session")) : null;
  function write(chat: string | null, session: string | null, replace = false) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (chat) next.set("chat", chat); else next.delete("chat");
      if (session) next.set("session", session); else next.delete("session");
      return next;
    }, { replace });
  }
  useEffect(() => {
    if (!initialized || tenantId === null) return;
    if (previousTenant.current === null) { previousTenant.current = tenantId; return; }
    if (previousTenant.current === tenantId) return;
    previousTenant.current = tenantId;
    clearing.current = true;
    setParams((current) => { const next = new URLSearchParams(current); next.delete("chat"); next.delete("session"); return next; }, { replace: true });
  }, [initialized, tenantId, setParams]);
  return {
    chatId, sessionId, bound, tenantId,
    select: (id: string, replace = false) => write(resourceId(id), null, replace),
    selectSession: (id: string, replace = false) => write(chatId, resourceId(id), replace),
    newChat: (replace = false) => write(chatId, null, replace), clear: () => write(null, null, true),
  };
}
