import type { CategorizeConfig } from '../../types';
import { Plus, Trash2 } from 'lucide-react';

interface CategorizeFormProps {
  config: CategorizeConfig;
  onChange: (updates: Partial<CategorizeConfig>) => void;
}

export const CategorizeForm = ({ config, onChange }: CategorizeFormProps) => {
  const categories = config.categories || ['category_1', 'category_2'];

  const updateCategory = (index: number, value: string) => {
    const newCategories = [...categories];
    newCategories[index] = value;
    onChange({ categories: newCategories });
  };

  const removeCategory = (index: number) => {
    onChange({ categories: categories.filter((_, i) => i !== index) });
  };

  const addCategory = () => {
    onChange({
      categories: [...categories, `category_${categories.length + 1}`]
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-medium text-gray-700">Categories</label>
          <button
            type="button"
            onClick={addCategory}
            className="flex items-center text-xs text-blue-600 hover:text-blue-800"
          >
            <Plus className="w-3 h-3 mr-1" /> Add
          </button>
        </div>
        
        <div className="space-y-2">
          {categories.map((cat, idx) => (
            <div key={idx} className="flex items-center space-x-2">
              <input
                type="text"
                className="flex-1 border-gray-300 rounded shadow-sm border p-2 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
                value={cat}
                onChange={(e) => updateCategory(idx, e.target.value)}
                placeholder="category_name"
              />
              <button
                type="button"
                onClick={() => removeCategory(idx)}
                className="text-gray-400 hover:text-red-500 p-1"
                title="Remove category"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          {categories.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-2 border border-dashed rounded-md">
              No categories defined
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
