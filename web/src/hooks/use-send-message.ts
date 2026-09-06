import { useState, useRef, useCallback } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getToken } from '../utils/authorization-util';
import { useQueryClient } from '@tanstack/react-query';

export interface UseSendMessageProps {
  sessionId: string;
}

export const useSendMessage = ({ sessionId }: UseSendMessageProps) => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamingMessage, setStreamingMessage] = useState<string>('');
  
  const queryClient = useQueryClient();
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (message: string) => {
    if (isStreaming) return;

    setIsStreaming(true);
    setError(null);
    setStreamingMessage('');

    abortControllerRef.current = new AbortController();
    const token = getToken();

    // Optimistically update the cache to include the user message
    const tempUserMessageId = `temp-user-${Date.now()}`;
    queryClient.setQueryData(['chat_history', sessionId], (old: any) => {
      const messages = old || [];
      return [
        ...messages,
        {
          id: tempUserMessageId,
          session_id: sessionId,
          role: 'user',
          content: message,
          created_at: new Date().toISOString(),
        }
      ];
    });

    let currentText = '';

    try {
      await fetchEventSource('/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: message,
        }),
        signal: abortControllerRef.current.signal,
        onmessage(ev) {
          if (ev.data === '[DONE]') {
            return;
          }
          
          try {
            const data = JSON.parse(ev.data);
            if (data.error) {
              throw new Error(data.error);
            }
            if (data.text) {
              currentText += data.text;
              setStreamingMessage(currentText);
            }
          } catch (e) {
            console.error('Error parsing SSE event', e);
            throw e;
          }
        },
        onclose() {
          // Normal stream close
        },
        onerror(err) {
          console.error('SSE Error:', err);
          setError(err?.message || 'Connection interrupted');
          // Don't throw if we want it to just stop and report error
          throw err;
        }
      });
      
      // Successfully finished
      // Refresh the history cache to ensure we get the finalized DB states (assistant + user)
      await queryClient.invalidateQueries({ queryKey: ['chat_history', sessionId] });
      setStreamingMessage('');

    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Stream failed');
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [sessionId, isStreaming, queryClient]);

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  return {
    sendMessage,
    isStreaming,
    streamingMessage,
    error,
    cancel
  };
};
