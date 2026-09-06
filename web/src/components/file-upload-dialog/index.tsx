import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, X, File, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useUploadDocument } from '../../hooks/use-knowledge-request';

interface FileUploadDialogProps {
  datasetId: string;
  onClose: () => void;
}

interface UploadingFile {
  file: File;
  progress: number;
  status: 'queued' | 'uploading' | 'completed' | 'failed';
  error?: string;
}

export const FileUploadDialog = ({ datasetId, onClose }: FileUploadDialogProps) => {
  const [files, setFiles] = useState<UploadingFile[]>([]);
  const uploadMutation = useUploadDocument();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map((file) => ({
      file,
      progress: 0,
      status: 'queued' as const,
    }));
    setFiles((prev) => [...prev, ...newFiles]);
    
    // Automatically start uploading the new files
    newFiles.forEach((f) => uploadFile(f.file));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const uploadFile = async (file: File) => {
    // Basic validation
    if (file.size > 50 * 1024 * 1024) {
      setFiles((prev) =>
        prev.map((f) =>
          f.file === file ? { ...f, status: 'failed', error: 'File exceeds 50MB limit' } : f
        )
      );
      return;
    }

    setFiles((prev) =>
      prev.map((f) => (f.file === file ? { ...f, status: 'uploading' } : f))
    );

    try {
      await uploadMutation.mutateAsync({
        datasetId,
        file,
        onProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1));
          setFiles((prev) =>
            prev.map((f) => (f.file === file ? { ...f, progress: percentCompleted } : f))
          );
        },
      });

      setFiles((prev) =>
        prev.map((f) => (f.file === file ? { ...f, status: 'completed', progress: 100 } : f))
      );
    } catch (err: any) {
      setFiles((prev) =>
        prev.map((f) =>
          f.file === file
            ? { ...f, status: 'failed', error: err.response?.data?.error || 'Upload failed' }
            : f
        )
      );
    }
  };

  const hasUploading = files.some((f) => f.status === 'uploading');

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-center p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900">Upload Documents</h2>
          <button
            onClick={onClose}
            disabled={hasUploading}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto">
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
              isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:bg-gray-50'
            }`}
          >
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-700 font-medium">Drag & Drop files here</p>
            <p className="text-gray-500 text-sm mt-1">or click to browse files</p>
            <p className="text-xs text-gray-400 mt-2">Maximum file size: 50MB</p>
          </div>

          {files.length > 0 && (
            <div className="mt-6 space-y-3">
              <h3 className="text-sm font-medium text-gray-900">Upload Queue</h3>
              {files.map((f, idx) => (
                <div key={idx} className="border rounded-lg p-4 bg-gray-50 flex items-center space-x-4">
                  <div className="bg-white p-2 rounded shadow-sm">
                    <File className="w-6 h-6 text-blue-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-sm font-medium text-gray-900 truncate">
                        {f.file.name}
                      </span>
                      <span className="text-xs text-gray-500">
                        {(f.file.size / (1024 * 1024)).toFixed(2)} MB
                      </span>
                    </div>
                    
                    {f.status === 'uploading' && (
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${f.progress}%` }}
                        />
                      </div>
                    )}

                    {f.status === 'failed' && (
                      <div className="text-xs text-red-600 flex items-center mt-1">
                        <AlertCircle className="w-3 h-3 mr-1" />
                        {f.error}
                        <button 
                          className="ml-2 text-blue-600 hover:underline"
                          onClick={() => uploadFile(f.file)}
                        >
                          Retry
                        </button>
                      </div>
                    )}

                    {f.status === 'completed' && (
                      <div className="text-xs text-green-600 flex items-center mt-1">
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Completed
                      </div>
                    )}
                  </div>
                  
                  <div className="flex-shrink-0">
                    {f.status === 'uploading' && <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />}
                    {f.status === 'completed' && <CheckCircle className="w-5 h-5 text-green-500" />}
                    {f.status === 'failed' && <AlertCircle className="w-5 h-5 text-red-500" />}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-6 border-t bg-gray-50 flex justify-end">
          <button
            onClick={onClose}
            disabled={hasUploading}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-medium rounded-md transition-colors disabled:opacity-50"
          >
            {hasUploading ? 'Uploading...' : 'Close'}
          </button>
        </div>
      </div>
    </div>
  );
};
