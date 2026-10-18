import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { useParseDocumentsRequest, useSetDocumentsEnabledRequest } from "@/hooks/use-document-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { ConfirmCount, DocumentView } from "@/services/document-service";
import { notifyError } from "@/services/notify";
import { cancelFailureOf, confirmCountsOf, parseFailureOf, switchFailureOf, type Placed } from "./errors";

/** The documents a refused re-parse would overwrite, with the ids to resend and what to do once they are replaced. */
export interface PendingConfirm {
  /** Counts up with every opening, so a dialog's own state (its error) never carries over to the next opening (FE-04). */
  session: number;
  ids: string[];
  documents: ConfirmCount[];
  onDone?: () => void;
}

/** What pressing "Replace chunks" led to. `counts` means the server answered with fresh numbers and the dialog stays. */
export type ReplaceOutcome = { kind: "done" } | { kind: "counts" } | { kind: "busy" } | { kind: "failed"; key: string };

export interface ParseActions {
  /** A parse or cancel request that includes this document is in flight. */
  isBusy(id: string): boolean;
  /** The search switch of this document is waiting for the server. */
  isSwitching(id: string): boolean;
  /** One request for all ids. A 409 `confirm_required` opens the confirmation instead of failing. */
  parse(ids: string[], onDone?: () => void): Promise<void>;
  cancel(ids: string[], onDone?: () => void): Promise<void>;
  setEnabled(id: string, enabled: boolean): Promise<void>;
  confirm: PendingConfirm | null;
  replace(): Promise<ReplaceOutcome>;
  dismiss(): void;
}

function useInFlight(): { has: (id: string) => boolean; claim: (ids: string[]) => boolean; release: (ids: string[]) => void } {
  const ids = useRef<Set<string>>(new Set());
  const [, setVersion] = useState(0);
  return {
    has: (id) => ids.current.has(id),
    claim: (wanted) => {
      if (wanted.length === 0 || wanted.some((id) => ids.current.has(id))) return false;
      for (const id of wanted) ids.current.add(id);
      setVersion((v) => v + 1);
      return true;
    },
    release: (wanted) => {
      for (const id of wanted) ids.current.delete(id);
      setVersion((v) => v + 1);
    },
  };
}

/**
 * The parse, cancel, re-parse and search-switch actions of a dataset's table. The SPA never decides whether a re-parse
 * needs confirmation: every start is sent without `confirm_replace`, and only a 409 `confirm_required` opens the dialog
 * with the server's counts. Failures are toasts with fixed copy chosen by `errors.ts`; the lists refresh in the
 * mutations' `onSettled`, so a request that timed out on the client is refetched too (FE-03).
 */
export function useParseActions(datasetId: string): ParseActions {
  const { t } = useTranslation();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const workspaceName = useWorkspaceName(tenantId ?? "");
  const parseRequest = useParseDocumentsRequest();
  const switchRequest = useSetDocumentsEnabledRequest();
  const running = useInFlight();
  const switching = useInFlight();
  const replacing = useRef(false);
  const [confirm, setConfirm] = useState<PendingConfirm | null>(null);
  const confirmRef = useRef<PendingConfirm | null>(null);
  const sessions = useRef(0);
  confirmRef.current = confirm;

  const toast = useCallback(
    (placed: Placed): void => {
      if (placed.key === null) return;
      notifyError({ id: `row:${placed.key}`, title: t(placed.key, { workspace: workspaceName }), description: "" });
    },
    [t, workspaceName],
  );

  async function send(ids: string[], mode: "1" | "2", onDone?: () => void): Promise<void> {
    if (!running.claim(ids)) return;
    try {
      await parseRequest.mutateAsync({ datasetId, ids, run: mode });
      onDone?.();
    } catch (error) {
      const counts = mode === "1" ? confirmCountsOf(error) : [];
      if (counts.length > 0) setConfirm({ session: (sessions.current += 1), ids, documents: counts, onDone });
      else toast(mode === "1" ? parseFailureOf(error) : cancelFailureOf(error));
    } finally {
      running.release(ids);
    }
  }

  async function replace(): Promise<ReplaceOutcome> {
    const current = confirmRef.current;
    if (current === null || replacing.current) return { kind: "busy" };
    replacing.current = true;
    try {
      await parseRequest.mutateAsync({ datasetId, ids: current.ids, run: "1", confirmReplace: true });
      setConfirm(null);
      current.onDone?.();
      return { kind: "done" };
    } catch (error) {
      const counts = confirmCountsOf(error);
      if (counts.length > 0) {
        setConfirm({ ...current, documents: counts });
        return { kind: "counts" };
      }
      const placed = parseFailureOf(error);
      if (placed.key === null) {
        // Someone else started it meanwhile: nothing is left to confirm.
        setConfirm(null);
        return { kind: "done" };
      }
      return { kind: "failed", key: placed.key };
    } finally {
      replacing.current = false;
    }
  }

  async function setEnabled(id: string, enabled: boolean): Promise<void> {
    if (!switching.claim([id])) return;
    try {
      await switchRequest.mutateAsync({ datasetId, ids: [id], enabled });
    } catch (error) {
      toast(switchFailureOf(error));
    } finally {
      switching.release([id]);
    }
  }

  return {
    isBusy: running.has,
    isSwitching: switching.has,
    parse: (ids, onDone) => send(ids, "1", onDone),
    cancel: (ids, onDone) => send(ids, "2", onDone),
    setEnabled,
    confirm,
    replace,
    dismiss: () => setConfirm(null),
  };
}

type Announced = Pick<DocumentView, "id" | "name" | "run" | "chunkCount">;

/**
 * Text for the polite live region: one sentence for every row whose `run` changed since the previous list, never a
 * percentage and never on the first list (nothing is known to have changed then).
 */
export function useParseAnnouncements(items: readonly Announced[] | undefined): string {
  const { t } = useTranslation();
  const previous = useRef<Map<string, string> | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (items === undefined) return;
    const next = new Map(items.map((item) => [item.id, item.run] as const));
    const before = previous.current;
    previous.current = next;
    if (before === null) return;
    const lines: string[] = [];
    for (const item of items) {
      const was = before.get(item.id);
      if (was === undefined || was === item.run) continue;
      if (item.run === "1") lines.push(t("datasets.parse.live.started", { name: item.name }));
      else if (item.run === "3") lines.push(t("datasets.parse.live.finished", { name: item.name, count: item.chunkCount }));
      else if (item.run === "4") lines.push(t("datasets.parse.live.failed", { name: item.name }));
      else if (item.run === "2") lines.push(t("datasets.parse.live.cancelled", { name: item.name }));
    }
    if (lines.length > 0) setMessage(lines.join(". "));
  }, [items, t]);
  return message;
}
