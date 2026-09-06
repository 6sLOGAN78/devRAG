import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatPage } from './index';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as authUtils from '../../utils/authorization-util';
import React from 'react';
import MockAdapter from 'axios-mock-adapter';
import { apiClient } from '../../utils/authorization-util';

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

describe('ChatPage E2E Simulation', () => {
  let mock: MockAdapter;

  beforeEach(() => {
    vi.clearAllMocks();
    mock = new MockAdapter(apiClient);
    
    // Mock token
    vi.spyOn(authUtils, 'getToken').mockReturnValue('fake-token');
    
    mock.onGet('/chat/session').reply(200, {
      data: [{ id: 'session-1', title: 'Test Session', created_at: '', updated_at: '', user_id: '', tenant_id: '', agent_id: '' }]
    });
    
    mock.onGet('/chat/message/session-1').reply(200, {
      data: []
    });
  });

  it('handles the complete chat flow with incremental streaming', async () => {
    const mockFetch = fetchEventSource as unknown as ReturnType<typeof vi.fn>;
    
    render(<ChatPage />, { wrapper: createWrapper() });
    
    // Wait for the session to load
    const sessionTitle = await screen.findAllByText('Test Session');
    expect(sessionTitle[0]).toBeInTheDocument();
    
    const input = await screen.findByRole('textbox', { name: 'Message Input' });
    
    // Mock the SSE stream response BEFORE firing the event
    mockFetch.mockImplementation(async (_url, options) => {
      setTimeout(() => {
        options.onmessage({ data: JSON.stringify({ text: "Hello" }) });
      }, 10);
      setTimeout(() => {
        options.onmessage({ data: JSON.stringify({ text: " from" }) });
      }, 20);
      setTimeout(() => {
        options.onmessage({ data: JSON.stringify({ text: " the bot" }) });
      }, 30);
      setTimeout(() => {
        options.onmessage({ data: "[DONE]" });
        // The SSE hook will call invalidateQueries, which fetches history again.
        mock.onGet('/chat/message/session-1').reply(200, {
          data: [
            { id: 'msg-1', session_id: 'session-1', role: 'user', content: 'Hello bot' },
            { id: 'msg-2', session_id: 'session-1', role: 'assistant', content: 'Hello from the bot' }
          ]
        });
      }, 40);
    });

    fireEvent.change(input, { target: { value: 'Hello bot' } });
    
    const sendButton = screen.getByLabelText('Send message');
    act(() => {
      fireEvent.click(sendButton);
    });
    
    // Optimistic user message appears via query data mutation
    expect(await screen.findByText('Hello bot')).toBeInTheDocument();
    
    // Wait for first chunk
    await act(async () => {
      await new Promise(r => setTimeout(r, 15));
    });
    expect(await screen.findByText('Hello')).toBeInTheDocument();
    
    // Wait for second chunk
    await act(async () => {
      await new Promise(r => setTimeout(r, 15));
    });
    expect(await screen.findByText('Hello from')).toBeInTheDocument();
    
    // Wait for completion (triggers invalidation and re-render)
    await act(async () => {
      await new Promise(r => setTimeout(r, 40)); // allow time for react-query to re-fetch
    });
    
    // Final text "Hello from the bot" is rendered
    expect(await screen.findByText('Hello from the bot')).toBeInTheDocument();
  });
});
