import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DatasetListPage } from './index';
import { DatasetDetailPage } from './detail';
import { apiClient } from '../../utils/authorization-util';
import MockAdapter from 'axios-mock-adapter';
import userEvent from '@testing-library/user-event';

describe('Knowledge UI Integration', () => {
  let mockAxios: MockAdapter;
  let queryClient: QueryClient;

  beforeEach(() => {
    mockAxios = new MockAdapter(apiClient);
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  afterEach(() => {
    mockAxios.restore();
    vi.clearAllMocks();
  });

  const TestApp = ({ initialRoute = '/datasets' }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/datasets" element={<DatasetListPage />} />
          <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  it('renders dataset list and empty state', async () => {
    mockAxios.onGet('/dataset/list').reply(200, { datasets: [] });

    render(<TestApp />);

    expect(screen.getByText('Knowledge Bases')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('No Knowledge Bases yet')).toBeInTheDocument();
    });
  });

  it('creates a new dataset', async () => {
    mockAxios.onGet('/dataset/list').reply(200, { datasets: [] });
    mockAxios.onPost('/dataset').reply(201, { id: 'test-1', name: 'Test KB', description: 'Desc' });

    render(<TestApp />);

    await waitFor(() => {
      expect(screen.getByText('No Knowledge Bases yet')).toBeInTheDocument();
    });

    const createBtns = screen.getAllByRole('button', { name: /Create Knowledge Base/i });
    fireEvent.click(createBtns[0]);

    // Modal appears
    expect(screen.getByRole('heading', { name: 'Create Knowledge Base' })).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText('e.g. Engineering Docs');
    const descInput = screen.getByPlaceholderText('Optional description');
    
    await userEvent.type(nameInput, 'Test KB');
    await userEvent.type(descInput, 'Desc');
    
    // intercept subsequent list call
    mockAxios.onGet('/dataset/list').reply(200, { 
      datasets: [{ id: 'test-1', name: 'Test KB', description: 'Desc', status: 'active', created_at: new Date().toISOString() }] 
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Create Knowledge Base' })).not.toBeInTheDocument();
    });

    // Dataset list should refresh and show the new DB
    await waitFor(() => {
      expect(screen.getByText('Test KB')).toBeInTheDocument();
    });
  });

  it('renders dataset detail and empty document list', async () => {
    mockAxios.onGet('/dataset/list').reply(200, { 
      datasets: [{ id: 'ds-1', name: 'Detail KB', status: 'active', created_at: new Date().toISOString() }] 
    });
    mockAxios.onGet('/document/list?dataset_id=ds-1').reply(200, { documents: [] });

    render(<TestApp initialRoute="/datasets/ds-1" />);

    await waitFor(() => {
      expect(screen.getByText('Detail KB')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText('No documents yet')).toBeInTheDocument();
    });
  });

  it('renders documents and allows deletion', async () => {
    mockAxios.onGet('/dataset/list').reply(200, { 
      datasets: [{ id: 'ds-1', name: 'Detail KB', status: 'active', created_at: new Date().toISOString() }] 
    });
    mockAxios.onGet('/document/list?dataset_id=ds-1').reply(200, { 
      documents: [{
        id: 'doc-1',
        name: 'test.pdf',
        size: 1048576,
        type: 'application/pdf',
        parse_status: 'completed'
      }] 
    });

    render(<TestApp initialRoute="/datasets/ds-1" />);

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
      expect(screen.getByText('1.00 MB')).toBeInTheDocument();
    });

    // delete
    mockAxios.onDelete('/document/doc-1').reply(200);
    // intercept reload
    mockAxios.onGet('/document/list?dataset_id=ds-1').reply(200, { documents: [] });

    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    const deleteBtn = screen.getByTitle('Delete Document');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.queryByText('test.pdf')).not.toBeInTheDocument();
    });
  });
});
