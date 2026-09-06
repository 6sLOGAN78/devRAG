import type { LLMConfig } from '../../types';

interface LLMFormProps {
  config: LLMConfig;
  onChange: (updates: Partial<LLMConfig>) => void;
}

export const LLMForm = ({ config, onChange }: LLMFormProps) => {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
        <select
          className="w-full border-gray-300 rounded-md shadow-sm border p-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm bg-white"
          value={config.model || ''}
          onChange={(e) => onChange({ model: e.target.value })}
        >
          <option value="">Select a model...</option>
          <optgroup label="Google (Gemini)">
            <option value="gemini/gemini-3.8-flash">Gemini 3.8 Flash</option>
            <option value="gemini/gemini-3.7-flash">Gemini 3.7 Flash</option>
            <option value="gemini/gemini-3.5-flash">Gemini 3.5 Flash</option>
            <option value="gemini/gemini-2.5-pro">Gemini 2.5 Pro</option>
            <option value="gemini/gemini-2.5-flash">Gemini 2.5 Flash</option>
          </optgroup>
          <optgroup label="OpenAI">
            <option value="gpt-4o">gpt-4o</option>
            <option value="gpt-4o-mini">gpt-4o-mini</option>
          </optgroup>
          <optgroup label="Anthropic">
            <option value="claude-3-5-sonnet">claude-3-5-sonnet</option>
            <option value="claude-3-haiku">claude-3-haiku</option>
          </optgroup>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt</label>
        <textarea
          className="w-full border-gray-300 rounded-md shadow-sm border p-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm font-mono"
          rows={6}
          value={config.system_prompt || ''}
          onChange={(e) => onChange({ system_prompt: e.target.value })}
          placeholder="You are a helpful assistant..."
        />
      </div>

      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="block text-sm font-medium text-gray-700">Temperature</label>
          <span className="text-xs text-gray-500">{config.temperature !== undefined ? config.temperature : 0.7}</span>
        </div>
        <input
          type="range"
          min="0"
          max="2"
          step="0.1"
          className="w-full"
          value={config.temperature !== undefined ? config.temperature : 0.7}
          onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
        />
      </div>
    </div>
  );
};
