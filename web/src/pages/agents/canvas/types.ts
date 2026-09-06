export type NodeTypeType = 'llm' | 'retrieval' | 'code' | 'switch' | 'categorize';

export type NodeStatus = 'idle' | 'running' | 'success' | 'error';

export interface CanvasNodeData extends Record<string, unknown> {
  label?: string;
  description?: string;
  status?: NodeStatus;
  config?: any; // To be expanded in 08-03
  routes?: string[]; // For categorize or custom switch routes
}

export type NodeDefinition = {
  type: NodeTypeType;
  label: string;
  description?: string;
};
