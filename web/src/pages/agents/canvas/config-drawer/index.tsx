import { useState, useEffect } from 'react';
import { useReactFlow, useNodes, useOnSelectionChange} from '@xyflow/react';
import { X, Settings2 } from 'lucide-react';
import type { CanvasNodeData, AnyNodeConfig } from '../types';

import { LLMForm } from './forms/LLMForm';
import { RetrievalForm } from './forms/RetrievalForm';
import { CodeForm } from './forms/CodeForm';
import { SwitchForm } from './forms/SwitchForm';
import { CategorizeForm } from './forms/CategorizeForm';

export const ConfigDrawer = () => {
  const { setNodes } = useReactFlow();
  const nodes = useNodes();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useOnSelectionChange({
    onChange: ({ nodes }) => {
      const selected = nodes.filter(n => n.selected);
      if (selected.length === 1) {
        setSelectedNodeId(selected[0].id);
      } else {
        setSelectedNodeId(null);
      }
    },
  });

  // Handle case where node is deleted
  useEffect(() => {
    if (selectedNodeId && !nodes.find(n => n.id === selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [nodes, selectedNodeId]);

  if (!selectedNodeId) {
    return null; // Don't render drawer if nothing selected
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  if (!selectedNode) return null;

  const nodeData = selectedNode.data as CanvasNodeData;
  const config = nodeData.config || {};
  const nodeType = selectedNode.type;

  const handleConfigChange = (updates: Partial<AnyNodeConfig>) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === selectedNodeId) {
          const currentData = n.data as CanvasNodeData;
          return {
            ...n,
            data: {
              ...currentData,
              config: {
                ...(currentData.config || {}),
                ...updates,
              },
            },
          };
        }
        return n;
      })
    );
  };

  const renderForm = () => {
    switch (nodeType) {
      case 'llm':
        return <LLMForm config={config as any} onChange={handleConfigChange} />;
      case 'retrieval':
        return <RetrievalForm config={config as any} onChange={handleConfigChange} />;
      case 'code':
        return <CodeForm config={config as any} onChange={handleConfigChange} />;
      case 'switch':
        return <SwitchForm config={config as any} onChange={handleConfigChange} />;
      case 'categorize':
        return <CategorizeForm config={config as any} onChange={handleConfigChange} />;
      default:
        return (
          <div className="text-sm text-gray-500">
            Unsupported node configuration ({nodeType})
          </div>
        );
    }
  };

  return (
    <div className="w-80 border-l bg-white flex flex-col h-full shadow-lg z-10 relative">
      <div className="px-4 py-3 border-b flex justify-between items-center bg-gray-50">
        <div className="flex items-center space-x-2">
          <Settings2 className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold text-sm text-gray-700 capitalize">
            {nodeType} Configuration
          </h2>
        </div>
        <button
          onClick={() => setSelectedNodeId(null)}
          className="text-gray-400 hover:text-gray-700 transition-colors"
          title="Close drawer"
          aria-label="Close drawer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 bg-white">
        {renderForm()}
      </div>
    </div>
  );
};
