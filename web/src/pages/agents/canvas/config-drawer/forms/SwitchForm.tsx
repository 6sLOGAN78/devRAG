import type { SwitchConfig, SwitchCondition } from '../../types';
import { Plus, Trash2 } from 'lucide-react';

interface SwitchFormProps {
  config: SwitchConfig;
  onChange: (updates: Partial<SwitchConfig>) => void;
}

export const SwitchForm = ({ config, onChange }: SwitchFormProps) => {
  const conditions = config.conditions || [];
  const defaultRoute = config.default_route || 'default';

  const updateCondition = (index: number, field: keyof SwitchCondition, value: string) => {
    const newConditions = [...conditions];
    newConditions[index] = { ...newConditions[index], [field]: value };
    onChange({ conditions: newConditions });
  };

  const removeCondition = (index: number) => {
    onChange({ conditions: conditions.filter((_, i) => i !== index) });
  };

  const addCondition = () => {
    onChange({
      conditions: [...conditions, { expression: 'env.get("value") == True', route: `route_${conditions.length + 1}` }]
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-medium text-gray-700">Conditions</label>
          <button
            type="button"
            onClick={addCondition}
            className="flex items-center text-xs text-blue-600 hover:text-blue-800"
          >
            <Plus className="w-3 h-3 mr-1" /> Add
          </button>
        </div>
        
        <div className="space-y-3">
          {conditions.map((cond, idx) => (
            <div key={idx} className="border rounded-md p-3 bg-gray-50 relative">
              <button
                type="button"
                onClick={() => removeCondition(idx)}
                className="absolute top-2 right-2 text-gray-400 hover:text-red-500"
                title="Remove condition"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              
              <div className="space-y-2 mt-1">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Jinja2 Expression</label>
                  <input
                    type="text"
                    className="w-full border-gray-300 rounded shadow-sm border p-1.5 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
                    value={cond.expression}
                    onChange={(e) => updateCondition(idx, 'expression', e.target.value)}
                    placeholder="env.get('val') == 'yes'"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Route Identifier</label>
                  <input
                    type="text"
                    className="w-full border-gray-300 rounded shadow-sm border p-1.5 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
                    value={cond.route}
                    onChange={(e) => updateCondition(idx, 'route', e.target.value)}
                    placeholder="true_path"
                  />
                </div>
              </div>
            </div>
          ))}
          {conditions.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-2 border border-dashed rounded-md">
              No conditions defined
            </div>
          )}
        </div>
      </div>

      <div className="border-t pt-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">Default Route</label>
        <p className="text-xs text-gray-500 mb-2">Fallback route if no conditions match.</p>
        <input
          type="text"
          className="w-full border-gray-300 rounded shadow-sm border p-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm font-mono"
          value={defaultRoute}
          onChange={(e) => onChange({ default_route: e.target.value })}
        />
      </div>
    </div>
  );
};
