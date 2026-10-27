import { useUserStore } from "@/stores/user-store";
import { useActiveWorkspace } from "./use-workspaces";

export function canManageAssistant(createdBy: string, userId: string | null, role: string, permission: string): boolean {
  if (!userId) return false;
  return createdBy === userId || permission === "team" && (role === "owner" || role === "admin");
}
export function useAssistantPermissions(assistant: { createdBy: string; permission: string } | undefined): boolean {
  const userId = useUserStore((state) => state.user?.id ?? null);
  const role = useActiveWorkspace()?.role ?? "";
  return assistant !== undefined && canManageAssistant(assistant.createdBy, userId, role, assistant.permission);
}
