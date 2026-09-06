export type NodeTypeType = 'llm' | 'retrieval' | 'code' | 'switch' | 'categorize';

export type NodeStatus = 'idle' | 'running' | 'success' | 'error';

export interface LLMConfig {
  model?: string;
  system_prompt?: string;
  temperature?: number;
}

export interface RetrievalConfig {
  datasets?: string[];
  top_k?: number;
  similarity_threshold?: number;
}

export interface CodeConfig {
  code?: string;
}

export interface SwitchCondition {
  expression: string;
  route: string;
}

export interface SwitchConfig {
  conditions?: SwitchCondition[];
  default_route?: string;
}

export interface CategorizeConfig {
  categories?: string[];
}

export type AnyNodeConfig = LLMConfig | RetrievalConfig | CodeConfig | SwitchConfig | CategorizeConfig | Record<string, any>;

export interface CanvasNodeData extends Record<string, unknown> {
  label?: string;
  description?: string;
  status?: NodeStatus;
  config?: AnyNodeConfig;
  // deprecated: moving to config
  routes?: string[]; 
}

export type NodeDefinition = {
  type: NodeTypeType;
  label: string;
  description?: string;
};
