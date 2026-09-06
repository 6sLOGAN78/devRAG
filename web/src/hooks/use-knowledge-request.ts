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
