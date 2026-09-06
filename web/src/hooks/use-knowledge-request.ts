import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../utils/authorization-util';
import type { AxiosProgressEvent } from 'axios';

export interface Dataset {
  id: string;
  name: string;
  description: string;
  tenant_id: string;
  created_by: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: string;
  dataset_id: string;
  tenant_id: string;
  name: string;
  size: number;
  type: string;
  parse_status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export const useDatasets = () => {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: async () => {
      const response = await apiClient.get('/dataset/list');
      return response.data.datasets as Dataset[];
    },
  });
};

export const useCreateDataset = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; description?: string }) => {
      const response = await apiClient.post('/dataset', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    },
  });
};

export const useDeleteDataset = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await apiClient.delete(`/dataset/${id}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    },
  });
};

export const useDocuments = (datasetId: string) => {
  return useQuery({
    queryKey: ['documents', datasetId],
    queryFn: async () => {
      const response = await apiClient.get(`/document/list?dataset_id=${datasetId}`);
      return response.data.documents as Document[];
    },
    enabled: !!datasetId,
  });
};

export const useUploadDocument = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      datasetId,
      file,
      onProgress,
    }: {
      datasetId: string;
      file: File;
      onProgress?: (progressEvent: AxiosProgressEvent) => void;
    }) => {
      const formData = new FormData();
      formData.append('dataset_id', datasetId);
      formData.append('file', file);

      const response = await apiClient.post('/document/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: onProgress,
      });
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['documents', variables.datasetId] });
    },
  });
};

export const useDeleteDocument = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id }: { id: string; datasetId: string }) => {
      const response = await apiClient.delete(`/document/${id}`);
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['documents', variables.datasetId] });
    },
  });
};

export interface DocumentStatus {
  document_id: string;
  task_id: string;
  status: string;
  progress: number;
  error_msg: string | null;
  updated_at: string;
}

export const useDocumentStatuses = (documentIds: string[]) => {
  return useQuery({
    queryKey: ['document_statuses', documentIds],
    queryFn: async () => {
      if (!documentIds.length) return {};
      const response = await apiClient.get(`/document/status?document_ids=${documentIds.join(',')}`);
      return response.data.statuses as Record<string, DocumentStatus>;
    },
    enabled: documentIds.length > 0,
    // Poll every 3 seconds if any document is processing
    refetchInterval: (query) => {
      if (!query.state.data) return 3000;
      
      const statuses = Object.values(query.state.data);
      // If any task is 'unstart' or 'running', keep polling
      const isProcessing = statuses.some(s => s.status === 'unstart' || s.status === 'running');
      return isProcessing ? 3000 : false;
    }
  });
};
