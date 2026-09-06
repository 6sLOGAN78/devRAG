import type { CodeConfig } from '../../types';

interface CodeFormProps {
  config: CodeConfig;
  onChange: (updates: Partial<CodeConfig>) => void;
}

export const CodeForm = ({ config, onChange }: CodeFormProps) => {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Python Transform</label>
        <p className="text-xs text-gray-500 mb-2">
          Executes in a restricted sandbox. Input variables are available in the <code>env</code> dictionary.
        </p>
        <textarea
          className="w-full border-gray-300 rounded-md shadow-sm border p-3 focus:ring-blue-500 focus:border-blue-500 sm:text-sm font-mono whitespace-pre bg-gray-50"
          rows={12}
          value={config.code || 'def transform(env):\n    return env'}
          onChange={(e) => onChange({ code: e.target.value })}
          spellCheck={false}
        />
      </div>
    </div>
  );
};
