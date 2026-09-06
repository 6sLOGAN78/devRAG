import { Handle, Position } from '@xyflow/react';
import { Bot, Database, Code, GitBranch } from 'lucide-react';

const BaseNode = ({ label, icon, isSource = true, isTarget = true }: any) => {
  return (
    <div className="bg-white border-2 border-gray-200 rounded-md shadow-sm min-w-[150px]">
      {isTarget && (
        <Handle type="target" position={Position.Top} className="w-3 h-3 border-2 border-white bg-gray-400" />
      )}
      <div className="flex items-center space-x-2 px-3 py-2 bg-gray-50 border-b border-gray-100 rounded-t-md">
        {icon}
        <span className="font-semibold text-sm text-gray-700">{label}</span>
      </div>
      <div className="p-3 text-xs text-gray-500">
        Placeholder for configuration
      </div>
      {isSource && (
        <Handle type="source" position={Position.Bottom} className="w-3 h-3 border-2 border-white bg-blue-500" />
      )}
    </div>
  );
};

export const LLMNode = (props: any) => (
  <BaseNode label="LLM Node" icon={<Bot className="w-4 h-4 text-purple-500" />} {...props} />
);

export const RetrievalNode = (props: any) => (
  <BaseNode label="Retrieval Node" icon={<Database className="w-4 h-4 text-blue-500" />} {...props} />
);

export const CodeNode = (props: any) => (
  <BaseNode label="Code Node" icon={<Code className="w-4 h-4 text-green-500" />} {...props} />
);

export const SwitchNode = (props: any) => (
  <BaseNode label="Switch Node" icon={<GitBranch className="w-4 h-4 text-orange-500" />} {...props} />
);

export const nodeTypes = {
  llm: LLMNode,
  retrieval: RetrievalNode,
  code: CodeNode,
  switch: SwitchNode,
};
