import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import {
  Bot,
  Database,
  Code,
  GitBranch,
  ListTree,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock
} from 'lucide-react';
import type { CanvasNodeData, NodeStatus } from './types';

// ==========================================
// Base Components & Helpers
// ==========================================

const StatusIndicator = ({ status }: { status?: NodeStatus }) => {
  if (!status || status === 'idle') {
    return <span title="Status: Idle"><Clock className="w-4 h-4 text-gray-400" aria-label="Status: Idle" /></span>;
  }
  if (status === 'running') {
    return <span title="Status: Running"><Loader2 className="w-4 h-4 text-blue-500 animate-spin" aria-label="Status: Running" /></span>;
  }
  if (status === 'success') {
    return <span title="Status: Success"><CheckCircle2 className="w-4 h-4 text-green-500" aria-label="Status: Success" /></span>;
  }
  if (status === 'error') {
    return <span title="Status: Error"><XCircle className="w-4 h-4 text-red-500" aria-label="Status: Error" /></span>;
  }
  return null;
};

interface CustomNodeBaseProps extends NodeProps {
  icon: React.ReactNode;
  title: string;
  className?: string;
  children?: React.ReactNode;
}

const CustomNodeBase = memo(({ data, selected, icon, title, children }: CustomNodeBaseProps) => {
  const nodeData = data as CanvasNodeData;
  const status = nodeData.status || 'idle';

  return (
    <div
      className={`min-w-[220px] bg-white rounded-lg shadow-sm border-2 transition-all ${
        selected ? 'border-blue-500 shadow-md ring-2 ring-blue-500/20' : 'border-gray-200 hover:border-gray-300'
      } ${status === 'error' && !selected ? 'border-red-300' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100 bg-gray-50 rounded-t-md">
        <div className="flex items-center space-x-2">
          {icon}
          <span className="font-semibold text-sm text-gray-700">{nodeData.label || title}</span>
        </div>
        <StatusIndicator status={status} />
      </div>

      {/* Body */}
      <div className="p-3 text-xs text-gray-600 bg-white rounded-b-md relative">
        {children}
      </div>
    </div>
  );
});

// Default styled handles
const InputHandle = ({ id = 'input', top = '50%' }: { id?: string, top?: string | number }) => (
  <Handle
    type="target"
    position={Position.Left}
    id={id}
    style={{ top }}
    className="w-3 h-3 bg-white border-2 border-gray-400 !-left-1.5"
  />
);

const OutputHandle = ({ id = 'output', top = '50%' }: { id?: string, top?: string | number }) => (
  <Handle
    type="source"
    position={Position.Right}
    id={id}
    style={{ top }}
    className="w-3 h-3 bg-white border-2 border-blue-500 !-right-1.5"
  />
);

// ==========================================
// Specific Node Implementations
// ==========================================

export const LLMNodeUI = memo((props: NodeProps) => {
  return (
    <CustomNodeBase {...props} icon={<Bot className="w-4 h-4 text-purple-600" />} title="LLM">
      <InputHandle />
      <div className="space-y-1">
        <p className="text-gray-500 font-medium">Text Generation</p>
        <p className="text-gray-400 italic">Configuration pending...</p>
      </div>
      <OutputHandle />
    </CustomNodeBase>
  );
});

export const RetrievalNodeUI = memo((props: NodeProps) => {
  return (
    <CustomNodeBase {...props} icon={<Database className="w-4 h-4 text-blue-600" />} title="Retrieval">
      <InputHandle />
      <div className="space-y-1">
        <p className="text-gray-500 font-medium">Hybrid Search</p>
        <p className="text-gray-400 italic">No dataset selected</p>
      </div>
      <OutputHandle />
    </CustomNodeBase>
  );
});

export const CodeNodeUI = memo((props: NodeProps) => {
  return (
    <CustomNodeBase {...props} icon={<Code className="w-4 h-4 text-green-600" />} title="Code">
      <InputHandle />
      <div className="space-y-1">
        <p className="text-gray-500 font-medium">Python Transform</p>
      </div>
      <OutputHandle />
    </CustomNodeBase>
  );
});

export const SwitchNodeUI = memo((props: NodeProps) => {
  // Switch outputs: true, false, default for basic scaffolding
  // In Phase 07, SwitchNode evaluates an expression and returns a route.
  return (
    <CustomNodeBase {...props} icon={<GitBranch className="w-4 h-4 text-orange-600" />} title="Switch">
      <InputHandle />
      <div className="space-y-4">
        <p className="text-gray-500 font-medium mb-2">Condition Evaluation</p>
        
        {/* Branch handles */}
        <div className="relative flex flex-col space-y-4 text-right pr-2">
          <div className="relative">
            <span className="text-gray-600 font-mono">true</span>
            <OutputHandle id="true" top="50%" />
          </div>
          <div className="relative">
            <span className="text-gray-600 font-mono">false</span>
            <OutputHandle id="false" top="50%" />
          </div>
          <div className="relative">
            <span className="text-gray-600 font-mono">default</span>
            <OutputHandle id="default" top="50%" />
          </div>
        </div>
      </div>
    </CustomNodeBase>
  );
});

export const CategorizeNodeUI = memo((props: NodeProps) => {
  const data = props.data as CanvasNodeData;
  const categories = data.routes && data.routes.length > 0 ? data.routes : ['cat_1', 'cat_2'];
  
  return (
    <CustomNodeBase {...props} icon={<ListTree className="w-4 h-4 text-teal-600" />} title="Categorize">
      <InputHandle />
      <div className="space-y-4">
        <p className="text-gray-500 font-medium mb-2">LLM Classification</p>
        <div className="relative flex flex-col space-y-4 text-right pr-2">
          {categories.map((cat, idx) => (
            <div className="relative" key={idx}>
              <span className="text-gray-600 font-mono">{cat}</span>
              <OutputHandle id={cat} top="50%" />
            </div>
          ))}
        </div>
      </div>
    </CustomNodeBase>
  );
});

export const customNodeTypes = {
  llm: LLMNodeUI,
  retrieval: RetrievalNodeUI,
  code: CodeNodeUI,
  switch: SwitchNodeUI,
  categorize: CategorizeNodeUI,
};
