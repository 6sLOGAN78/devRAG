import React from 'react';
import type { NodeDefinition, NodeTypeType } from './types';
import { Bot, Database, Code, GitBranch } from 'lucide-react';

const NODE_DEFINITIONS: NodeDefinition[] = [
  { type: 'llm', label: 'LLM Node', description: 'Generates text using an LLM' },
  { type: 'retrieval', label: 'Retrieval Node', description: 'Searches knowledge base' },
  { type: 'code', label: 'Code Node', description: 'Executes Python code' },
  { type: 'switch', label: 'Switch Node', description: 'Conditional routing' },
];

const iconMap: Record<NodeTypeType, React.ReactNode> = {
  llm: <Bot className="w-5 h-5" />,
  retrieval: <Database className="w-5 h-5" />,
  code: <Code className="w-5 h-5" />,
  switch: <GitBranch className="w-5 h-5" />,
};

export const NodePalette = () => {
  const onDragStart = (event: React.DragEvent<HTMLDivElement>, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="w-64 bg-white border-r flex flex-col h-full shadow-sm">
      <div className="p-4 border-b bg-gray-50">
        <h2 className="font-semibold text-gray-700">Node Palette</h2>
        <p className="text-xs text-gray-500 mt-1">Drag nodes to the canvas</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {NODE_DEFINITIONS.map((def) => (
          <div
            key={def.type}
            className="border rounded-md p-3 bg-white hover:border-blue-400 hover:shadow-sm cursor-grab transition-all group flex items-start space-x-3"
            onDragStart={(event) => onDragStart(event, def.type)}
            draggable
          >
            <div className="text-gray-500 group-hover:text-blue-500 mt-0.5">
              {iconMap[def.type]}
            </div>
            <div>
              <div className="font-medium text-sm text-gray-700 group-hover:text-blue-700">{def.label}</div>
              <div className="text-xs text-gray-400 mt-1">{def.description}</div>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
};
