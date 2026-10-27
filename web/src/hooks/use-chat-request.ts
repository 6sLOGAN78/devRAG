import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { chatCompletionsPath } from "@/constants/api-paths";
import {
  createAssistant, deleteAssistant, deleteSession, getAssistant, getSession, listAssistants, listSessions, setFeedback, updateAssistant,
  type AssistantChanges, type Feedback,
} from "@/services/chat-service";
import { chatTurnReducer, decodeFrame, initialTurn } from "@/services/chat-turn";
import { ApiError } from "@/services/http";
import { postEventStream } from "@/services/sse";
import { useActiveWorkspace } from "./use-workspaces";

const validId = (id: string | undefined): id is string => typeof id === "string" && /^[a-f0-9]{32}$/.test(id);
export const chatRoot = (tenantId: string | null) => ["ws", tenantId, "chat"] as const;
export const assistantsKey = (tenantId: string | null, page: number, keywords: string) => [...chatRoot(tenantId), "assistants", page, keywords] as const;
export const assistantKey = (tenantId: string | null, chatId: string) => [...chatRoot(tenantId), "assistant", chatId] as const;
export const sessionsKey = (tenantId: string | null, chatId: string, page: number) => [...chatRoot(tenantId), "sessions", chatId, page] as const;
export const sessionKey = (tenantId: string | null, chatId: string, sessionId: string) => [...chatRoot(tenantId), "session", chatId, sessionId] as const;

export function useAssistantsRequest(page = 1, keywords = "", enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: assistantsKey(tenantId, page, keywords), queryFn: () => listAssistants(tenantId!, page, keywords), retry: false,
    // Previous pages are useful; previous workspaces must never be displayed during a switch.
    placeholderData: (data, query) => query?.queryKey[1] === tenantId ? keepPreviousData(data) : undefined,
    enabled: enabled && tenantId !== null,
  });
}
export function useAssistantRequest(chatId?: string, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({ queryKey: assistantKey(tenantId, chatId ?? ""), queryFn: () => getAssistant(chatId!), retry: false, enabled: enabled && tenantId !== null && validId(chatId) });
}
export function useSessionsRequest(chatId?: string, page = 1, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: sessionsKey(tenantId, chatId ?? "", page), queryFn: () => listSessions(chatId!, page), retry: false,
    placeholderData: (data, query) => query?.queryKey[1] === tenantId && query.queryKey[4] === chatId ? keepPreviousData(data) : undefined,
    enabled: enabled && tenantId !== null && validId(chatId),
  });
}
export function useSessionRequest(chatId?: string, sessionId?: string, before?: string, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: [...sessionKey(tenantId, chatId ?? "", sessionId ?? ""), before ?? "latest"],
    queryFn: () => getSession(chatId!, sessionId!, before), retry: false,
    enabled: enabled && tenantId !== null && validId(chatId) && validId(sessionId) && (before === undefined || validId(before)),
  });
}
function requireWorkspace(tenantId: string | null): string {
  if (!tenantId) throw new ApiError({ code: 400, status: 400, message: "Choose a workspace before sending a request.", data: { reason: "workspace_unknown" } });
  return tenantId;
}
function useChatMutation<T, R>(write: (input: T, tenantId: string) => Promise<R>) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const client = useQueryClient();
  return useMutation({ mutationFn: (input: T) => write(input, requireWorkspace(tenantId)), retry: false, gcTime: 0,
    onSettled: () => client.invalidateQueries({ queryKey: chatRoot(tenantId) }) });
}
export function useCreateAssistant() { return useChatMutation((changes: AssistantChanges, tenantId) => createAssistant(tenantId, changes)); }
export function useUpdateAssistant() { return useChatMutation(({ chatId, changes }: { chatId: string; changes: AssistantChanges }) => updateAssistant(chatId, changes)); }
export function useDeleteAssistant() { return useChatMutation((chatId: string) => deleteAssistant(chatId)); }
export function useDeleteSession() { return useChatMutation(({ chatId, sessionId }: { chatId: string; sessionId: string }) => deleteSession(chatId, sessionId)); }
export function useFeedback() {
  return useChatMutation(({ chatId, sessionId, messageId, thumb, comment }: { chatId: string; sessionId: string; messageId: string; thumb: Feedback; comment?: string }) => setFeedback(chatId, sessionId, messageId, thumb, comment));
}

/** One controller per turn. A draft's first session id may enter the URL without cancelling its stream. */
export function useChatTurn({ chatId, sessionId }: { chatId?: string; sessionId?: string }) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const client = useQueryClient();
  const [state, dispatch] = useReducer(chatTurnReducer, initialTurn);
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const liveSession = useRef<string | undefined>(undefined);
  const previousSelection = useRef(sessionId);
  useEffect(() => {
    epoch.current += 1;
    setPending(false);
    dispatch({ type: "reset" });
    return () => { epoch.current += 1; controller.current?.abort(); controller.current = null; liveSession.current = undefined; };
  }, [tenantId, chatId]);
  const stop = useCallback(() => controller.current?.abort(), []);
  const reset = useCallback(() => { epoch.current += 1; controller.current?.abort(); controller.current = null; liveSession.current = undefined; setPending(false); dispatch({ type: "reset" }); }, []);
  useEffect(() => {
    if (previousSelection.current === sessionId) return;
    previousSelection.current = sessionId;
    if (sessionId !== liveSession.current) reset();
  }, [sessionId, reset]);
  const send = useCallback(async (message: string): Promise<void> => {
    if (controller.current) return;
    const tenant = requireWorkspace(tenantId);
    if (!validId(chatId) || (sessionId !== undefined && !validId(sessionId))) throw new ApiError({ code: 400, status: 400, message: "Invalid chat selection.", data: { reason: "fields_invalid" } });
    const current = new AbortController(), generation = ++epoch.current;
    controller.current = current;
    setPending(true);
    liveSession.current = sessionId;
    let receivedFrame = false, finalFrame = false;
    dispatch({ type: "start", sessionId });
    try {
      const outcome = await postEventStream({
        url: chatCompletionsPath, body: { chat_id: chatId, ...(sessionId ? { session_id: sessionId } : {}), message, stream: true, tenant_id: tenant }, signal: current.signal,
        onFrame(raw) {
          if (generation !== epoch.current || current.signal.aborted) return;
          const frame = decodeFrame(raw);
          if (!frame) return;
          if (frame.data.session_id) liveSession.current = frame.data.session_id;
          receivedFrame = true; finalFrame ||= frame.data.final || frame.code !== 0;
          dispatch({ type: "frame", frame });
        },
      });
      if (generation === epoch.current) {
        if (outcome === "aborted") dispatch({ type: "abort" });
        else if (!finalFrame) throw new ApiError({ code: -1, status: 0, kind: "network", message: "The final answer frame is missing." });
      }
    } catch (error) {
      if (!receivedFrame) {
        if (generation === epoch.current) dispatch({ type: "reset" });
        throw error;
      }
      if (generation === epoch.current) dispatch({ type: "error", error });
    } finally {
      if (controller.current === current) { controller.current = null; setPending(false); }
      // The root includes assistant lists, session lists and all detail cursor pages.
      await client.invalidateQueries({ queryKey: chatRoot(tenant) });
    }
  }, [tenantId, chatId, sessionId, client]);
  return { state, pending, send, stop, reset };
}
