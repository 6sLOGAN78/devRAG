import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../utils/authorization-util';
import type { CanvasNodeData } from '../pages/agents/canvas/types';
import type { Node, Edge } from '@xyflow/react';

export interface CanvasGraph {
  nodes: Node<CanvasNodeData>[];
  edges: Edge[];
}

export interface SaveCanvasRequest {
  id: string;
  graph: CanvasGraph;
}

export interface GetCanvasResponse {
  id: string;
  graph: CanvasGraph;
}

export const useSaveCanvas = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (req: SaveCanvasRequest) => {
      const response = await apiClient.post('/agent/canvas/save', req);
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent_canvas', variables.id] });
    },
  });
};

export const useGetCanvas = (id: string) => {
  return useQuery({
    queryKey: ['agent_canvas', id],
    queryFn: async () => {
      const response = await apiClient.get(`/agent/canvas/${id}`);
      return response.data.data as GetCanvasResponse;
    },
    enabled: !!id,
    retry: false,
  });
};
