export type NodeTypeType = 'llm' | 'retrieval' | 'code' | 'switch';

export type NodeDefinition = {
  type: NodeTypeType;
  label: string;
  description?: string;
};
