import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDocumentStatuses } from './use-knowledge-request';
import { apiClient } from '../utils/authorization-util';
import MockAdapter from 'axios-mock-adapter';
import React from 'react';

const mock = new MockAdapter(apiClient);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe('useDocumentStatuses', () => {
  beforeEach(() => {
    mock.reset();
    queryClient.clear();
  });

  it('fetches document statuses correctly', async () => {
    mock.onGet('/document/status?document_ids=doc1,doc2').reply(200, {
      statuses: {
        doc1: {
          document_id: 'doc1',
          task_id: 'task1',
          status: 'running',
          progress: 50,
          error_msg: null,
          updated_at: '2023-01-01T00:00:00Z',
        },
        doc2: {
          document_id: 'doc2',
          task_id: 'task2',
          status: 'success',
          progress: 100,
          error_msg: null,
          updated_at: '2023-01-01T00:00:00Z',
        },
      },
    });

    const { result } = renderHook(() => useDocumentStatuses(['doc1', 'doc2']), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.doc1.progress).toBe(50);
    expect(result.current.data?.doc2.status).toBe('success');
  });

  it('skips fetching when array is empty', async () => {
    const { result } = renderHook(() => useDocumentStatuses([]), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });
});
