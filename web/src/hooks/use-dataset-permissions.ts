import { useUserStore } from "@/stores/user-store";
import { useWorkspaces } from "./use-workspaces";

/**
 * What the signed-in user may do with a dataset or one of its documents (D-09, D-27), derived from `createdBy`, the
 * signed-in user id and the caller's role in the dataset's workspace. The SPA only decides which controls to draw (a
 * control the caller may not use is absent, not disabled); the server stays authoritative and a 403 on a drawn control
 * shows the lost-permission alert and refetches.
 */

/** Roles that manage every dataset of their workspace. */
const MANAGER_ROLES: ReadonlySet<string> = new Set(["owner", "admin"]);

/** Dataset settings and delete: the creator, the workspace owner and admins. Never another member of a `team` dataset. */
export function canManageDataset(createdBy: string, userId: string | null, role: string): boolean {
  if (MANAGER_ROLES.has(role)) return true;
  return userId !== null && userId !== "" && createdBy !== "" && createdBy === userId;
}

/** Deleting one document: whoever may manage the dataset, or the member who uploaded the document. */
export function canRemoveDocument(datasetCreatedBy: string, documentCreatedBy: string, userId: string | null, role: string): boolean {
  return canManageDataset(datasetCreatedBy, userId, role) || (userId !== null && userId !== "" && documentCreatedBy !== "" && documentCreatedBy === userId);
}

/** The caller's role in one workspace: `owner`, `admin`, `normal`, or an empty string when they are not a member. */
export function useRoleIn(tenantId: string): string {
  return useWorkspaces().find((workspace) => workspace.tenantId === tenantId)?.role ?? "";
}

/** The display name of one workspace, or an empty string when the caller has none by that id. */
export function useWorkspaceName(tenantId: string): string {
  return useWorkspaces().find((workspace) => workspace.tenantId === tenantId)?.name ?? "";
}

/** True when the signed-in user may change or delete the dataset. */
export function useCanManageDataset(dataset: { createdBy: string; tenantId: string }): boolean {
  const userId = useUserStore((state) => state.user?.id ?? null);
  const role = useRoleIn(dataset.tenantId);
  return canManageDataset(dataset.createdBy, userId, role);
}

/** True when the signed-in user may delete this document (plan 03-31 draws the row control from it). */
export function useCanRemoveDocument(dataset: { createdBy: string; tenantId: string }, document: { createdBy: string }): boolean {
  const userId = useUserStore((state) => state.user?.id ?? null);
  const role = useRoleIn(dataset.tenantId);
  return canRemoveDocument(dataset.createdBy, document.createdBy, userId, role);
}
