import { render, screen } from '@testing-library/react';
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
    
    vi.spyOn(authUtils, 'getToken').mockReturnValue('fake-token');
    
    mock.onGet('/chat/session').reply(200, {
      data: [{ id: 'session-1', title: 'Test Session', created_at: '', updated_at: '', user_id: '', tenant_id: '', agent_id: '' }]
    });
    
    mock.onGet('/chat/message/session-1').reply(200, {
      data: []
    });
  });

  it('renders chat layout', async () => {
    render(<ChatPage />, { wrapper: createWrapper() });
    
    const sessionTitle = await screen.findAllByText('Test Session');
    expect(sessionTitle[0]).toBeInTheDocument();
    
    const input = await screen.findByRole('textbox', { name: 'Message Input' });
    expect(input).toBeInTheDocument();
  });
});
