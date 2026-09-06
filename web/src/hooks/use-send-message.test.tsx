import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useSendMessage } from './use-send-message';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock fetchEventSource
vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn(),
}));

import { fetchEventSource } from '@microsoft/fetch-event-source';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('useSendMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes correctly', () => {
    const { result } = renderHook(() => useSendMessage({ sessionId: '123' }), {
      wrapper: createWrapper(),
    });
    
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.streamingMessage).toBe('');
    expect(result.current.error).toBe(null);
  });

  it('updates streaming message incrementally', async () => {
    // We simulate the fetchEventSource calling onmessage multiple times
    const mockFetch = fetchEventSource as unknown as ReturnType<typeof vi.fn>;
    mockFetch.mockImplementation(async (_url, options) => {
      setTimeout(() => {
        options.onmessage({ data: JSON.stringify({ text: "Hello" }) });
      }, 10);
      setTimeout(() => {
        options.onmessage({ data: JSON.stringify({ text: " world" }) });
      }, 20);
      setTimeout(() => {
        options.onmessage({ data: "[DONE]" });
      }, 30);
    });

    const { result } = renderHook(() => useSendMessage({ sessionId: '123' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.sendMessage("Hi");
    });
    
    expect(result.current.isStreaming).toBe(true);

    // Wait for chunk 1
    await act(async () => {
      await new Promise(r => setTimeout(r, 15));
    });
    expect(result.current.streamingMessage).toBe('Hello');

    // Wait for chunk 2
    await act(async () => {
      await new Promise(r => setTimeout(r, 15));
    });
    expect(result.current.streamingMessage).toBe('Hello world');
    
    // Wait for completion
    await act(async () => {
      await new Promise(r => setTimeout(r, 15));
    });
    expect(result.current.isStreaming).toBe(false);
  });
  
  it('handles cancellation properly', () => {
    const { result } = renderHook(() => useSendMessage({ sessionId: '123' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.sendMessage("Hi");
    });
    
    expect(result.current.isStreaming).toBe(true);
    
    act(() => {
      result.current.cancel();
    });
    
    expect(result.current.isStreaming).toBe(false);
  });
});
