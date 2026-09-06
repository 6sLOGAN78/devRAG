import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../utils/authorization-util';

export interface ChatSession {
  id: string;
  user_id: string;
  tenant_id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  tenant_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: any | null;
  created_at: string;
  updated_at: string;
}

// Fetch all sessions
export const useChatSessions = () => {
  return useQuery({
    queryKey: ['chat_sessions'],
    queryFn: async () => {
      const response = await apiClient.get<{ data: ChatSession[] }>('/chat/session');
      return response.data.data;
    },
  });
};

// Create a new session
export const useCreateChatSession = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (req: { agent_id: string; title: string }) => {
      const response = await apiClient.post<{ data: ChatSession }>('/chat/session', req);
      return response.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat_sessions'] });
    },
  });
};

// Fetch message history
export const useChatHistory = (sessionId: string | null) => {
  return useQuery({
    queryKey: ['chat_history', sessionId],
    queryFn: async () => {
      const response = await apiClient.get<{ data: ChatMessage[] }>(`/chat/message/${sessionId}`);
      return response.data.data;
    },
    enabled: !!sessionId,
  });
};
