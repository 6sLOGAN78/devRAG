import React from 'react';
import { X, FileText } from 'lucide-react';

interface CitationData {
  chunk_id: string;
  document_id: string;
  content: string;
  source: string;
  page?: number;
  bbox?: number[];
  score?: number;
}

interface CitationViewerProps {
  citation: CitationData | null;
  citationIndex: number | null;
  onClose: () => void;
  isOpen: boolean;
}

export const CitationViewer: React.FC<CitationViewerProps> = ({ citation, citationIndex, onClose, isOpen }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-sm md:max-w-md bg-white shadow-2xl border-l z-50 flex flex-col transform transition-transform duration-300">
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div className="flex items-center space-x-2">
          <span className="flex items-center justify-center w-6 h-6 text-sm font-bold text-blue-700 bg-blue-100 rounded">
            {citationIndex !== null ? citationIndex + 1 : ''}
          </span>
          <h3 className="font-semibold text-gray-800">Source Details</h3>
        </div>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-gray-200 transition-colors">
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {citation ? (
          <>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">Source Document</span>
              <div className="flex items-start space-x-2 text-sm text-gray-800">
                <FileText className="w-4 h-4 mt-0.5 text-blue-600 flex-shrink-0" />
                <span className="break-words font-medium">{citation.source || citation.document_id}</span>
              </div>
              {citation.page !== undefined && (
                <div className="text-sm text-gray-600 mt-1 pl-6">
                  Page: {citation.page}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1 mt-4">
              <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">Relevant Passage</span>
              <div className="p-3 bg-gray-50 border rounded-lg text-sm text-gray-700 whitespace-pre-wrap leading-relaxed shadow-inner">
                {citation.content}
              </div>
            </div>

            {/* Document Preview Placeholder */}
            <div className="flex flex-col gap-1 mt-4 h-64 border rounded-lg overflow-hidden bg-gray-100 relative">
              <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 p-6 text-center">
                <FileText className="w-12 h-12 mb-2 text-gray-300" />
                <p className="text-sm">PDF viewer not implemented natively in this mock environment.</p>
                <p className="text-xs mt-2">Document ID: {citation.document_id}</p>
                {citation.bbox && (
                  <p className="text-xs mt-1">BBox: {JSON.stringify(citation.bbox)}</p>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            No citation details available.
          </div>
        )}
      </div>
    </div>
  );
};
