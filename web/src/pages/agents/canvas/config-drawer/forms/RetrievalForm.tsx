import type { RetrievalConfig } from '../../types';

interface RetrievalFormProps {
  config: RetrievalConfig;
  onChange: (updates: Partial<RetrievalConfig>) => void;
}

// Mock dataset API results
const MOCK_DATASETS = [
  { id: 'dataset-1', name: 'Internal Documentation' },
  { id: 'dataset-2', name: 'API References' },
  { id: 'dataset-3', name: 'Customer Support Logs' },
];

export const RetrievalForm = ({ config, onChange }: RetrievalFormProps) => {
  const selectedDatasets = config.datasets || [];

  const handleDatasetToggle = (id: string) => {
    if (selectedDatasets.includes(id)) {
      onChange({ datasets: selectedDatasets.filter(d => d !== id) });
    } else {
      onChange({ datasets: [...selectedDatasets, id] });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Knowledge Bases</label>
        <div className="space-y-2 max-h-48 overflow-y-auto border rounded-md p-2 bg-gray-50">
          {MOCK_DATASETS.map((ds) => (
            <label key={ds.id} className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={selectedDatasets.includes(ds.id)}
                onChange={() => handleDatasetToggle(ds.id)}
              />
              <span className="text-sm text-gray-700">{ds.name}</span>
            </label>
          ))}
          {MOCK_DATASETS.length === 0 && (
            <div className="text-xs text-gray-500 text-center py-2">No datasets available</div>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Results)</label>
        <input
          type="number"
          min="1"
          max="50"
          className="w-full border-gray-300 rounded-md shadow-sm border p-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          value={config.top_k || 5}
          onChange={(e) => onChange({ top_k: parseInt(e.target.value, 10) || 5 })}
        />
      </div>

      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="block text-sm font-medium text-gray-700">Similarity Threshold</label>
          <span className="text-xs text-gray-500">{config.similarity_threshold !== undefined ? config.similarity_threshold : 0.7}</span>
        </div>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          className="w-full"
          value={config.similarity_threshold !== undefined ? config.similarity_threshold : 0.7}
          onChange={(e) => onChange({ similarity_threshold: parseFloat(e.target.value) })}
        />
      </div>
    </div>
  );
};
