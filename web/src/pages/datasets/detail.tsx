import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { useDatasets, useDocuments, useDeleteDocument } from '../../hooks/use-knowledge-request';
import { Loader2, ArrowLeft, UploadCloud, File, Trash2 } from 'lucide-react';
import { FileUploadDialog } from '../../components/file-upload-dialog';

export const DatasetDetailPage = () => {
  const { datasetId } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();
  
  const { data: datasets, isLoading: isDatasetLoading } = useDatasets();
  const { data: documents, isLoading: isDocsLoading, error: docsError } = useDocuments(datasetId || '');
  const deleteDocMutation = useDeleteDocument();

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

  // Derive current dataset
  const dataset = datasets?.find((d) => d.id === datasetId);

  const handleDeleteDoc = async (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to delete document "${name}"?`)) {
      await deleteDocMutation.mutateAsync({ id, datasetId: datasetId! });
    }
  };

  if (isDatasetLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="max-w-6xl mx-auto py-6">
        <div className="bg-red-50 text-red-600 p-4 rounded-lg">
          Knowledge Base not found.
        </div>
        <button onClick={() => navigate('/datasets')} className="mt-4 text-blue-600 hover:underline">
          Return to Knowledge Bases
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto py-6 space-y-6">
      <div>
        <Link to="/datasets" className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to Knowledge Bases
        </Link>
        
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{dataset.name}</h1>
            {dataset.description && (
              <p className="mt-1 text-gray-500">{dataset.description}</p>
            )}
            <p className="mt-2 text-sm text-gray-400">
              Documents: {documents?.length || 0}
            </p>
          </div>
          
          <button
            onClick={() => setIsUploadModalOpen(true)}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm transition-colors"
          >
            <UploadCloud className="w-5 h-5" />
            <span>Upload Documents</span>
          </button>
        </div>
      </div>

      <hr className="border-gray-200" />

      <div>
        <h2 className="text-lg font-bold text-gray-900 mb-4">Documents</h2>
        
        {isDocsLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
          </div>
        ) : docsError ? (
          <div className="bg-red-50 text-red-600 p-4 rounded-lg">
            Failed to load documents.
          </div>
        ) : documents?.length === 0 ? (
          <div className="bg-white shadow rounded-lg p-12 text-center">
            <File className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No documents yet</h3>
            <p className="text-gray-500 mb-6">Upload a document to start building your Knowledge Base.</p>
            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-lg shadow-sm transition-colors"
            >
              <UploadCloud className="w-5 h-5" />
              <span>Upload Document</span>
            </button>
          </div>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {documents?.map((doc) => (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <File className="w-5 h-5 text-gray-400 mr-3" />
                        <div className="text-sm font-medium text-gray-900 truncate max-w-xs">{doc.name}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {doc.type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {(doc.size / (1024 * 1024)).toFixed(2)} MB
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        doc.parse_status === 'completed' ? 'bg-green-100 text-green-800' :
                        doc.parse_status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`}>
                        {doc.parse_status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => handleDeleteDoc(doc.id, doc.name)}
                        className="text-red-600 hover:text-red-900"
                        title="Delete Document"
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
      </div>

      {isUploadModalOpen && (
        <FileUploadDialog
          datasetId={dataset.id}
          onClose={() => setIsUploadModalOpen(false)}
        />
      )}
    </div>
  );
};
