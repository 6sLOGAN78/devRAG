import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Loader2, Plus, Database, Trash2 } from 'lucide-react';
import { useDatasets, useCreateDataset, useDeleteDataset } from '../../hooks/use-knowledge-request';

export const DatasetListPage = () => {
  const navigate = useNavigate();
  const { data: datasets, isLoading, error } = useDatasets();
  const deleteMutation = useDeleteDataset();
  
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const handleDelete = async (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to delete "${name}"?`)) {
      await deleteMutation.mutateAsync(id);
    }
  };

  return (
    <div className="max-w-6xl mx-auto py-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Knowledge Bases</h1>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm transition-colors"
        >
          <Plus className="w-5 h-5" />
          <span>Create Knowledge Base</span>
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg">
          Failed to load Knowledge Bases.
        </div>
      ) : datasets?.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-12 text-center">
          <Database className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Knowledge Bases yet</h3>
          <p className="text-gray-500 mb-6">Create your first Knowledge Base to start uploading documents.</p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-lg shadow-sm transition-colors"
          >
            <Plus className="w-5 h-5" />
            <span>Create Knowledge Base</span>
          </button>
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created At
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {datasets?.map((dataset) => (
                <tr 
                  key={dataset.id} 
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/datasets/${dataset.id}`)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{dataset.name}</div>
                    {dataset.description && (
                      <div className="text-sm text-gray-500">{dataset.description}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                      {dataset.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(dataset.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(dataset.id, dataset.name);
                      }}
                      className="text-red-600 hover:text-red-900 p-1"
                      title="Delete Dataset"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isCreateModalOpen && (
        <CreateDatasetModal onClose={() => setIsCreateModalOpen(false)} />
      )}
    </div>
  );
};

const CreateDatasetModal = ({ onClose }: { onClose: () => void }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const createMutation = useCreateDataset();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');

    const trimmedName = name.trim();
    if (!trimmedName) {
      setErrorMsg('Name is required');
      return;
    }

    try {
      await createMutation.mutateAsync({ name: trimmedName, description: description.trim() });
      onClose();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.error || 'Failed to create Knowledge Base');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Create Knowledge Base</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMsg && (
            <div className="bg-red-50 text-red-600 px-4 py-2 rounded text-sm">
              {errorMsg}
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name *
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="e.g. Engineering Docs"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 h-24 resize-none"
              placeholder="Optional description"
            />
          </div>

          <div className="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-md transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md flex items-center space-x-2 transition-colors disabled:opacity-50"
            >
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              <span>Create</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
