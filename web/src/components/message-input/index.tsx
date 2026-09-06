import React, { useState, useRef, useEffect } from 'react';
import type { KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';

interface MessageInputProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
}

export const MessageInput: React.FC<MessageInputProps> = ({ 
  onSend, 
  onCancel,
  disabled = false, 
  isStreaming = false,
  placeholder = "Type a message..." 
}) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || isStreaming) return;
    
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isSubmitDisabled = !value.trim() || disabled;

  return (
    <div className="relative w-full max-w-4xl mx-auto flex items-end gap-2 bg-white border border-gray-300 rounded-xl shadow-sm p-2 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500 transition-shadow">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled && !isStreaming}
        className="w-full max-h-[200px] bg-transparent border-0 focus:ring-0 resize-none p-2 py-2 m-0 text-gray-800 placeholder-gray-400 focus:outline-none overflow-y-auto"
        rows={1}
        aria-label="Message Input"
      />
      <div className="flex-shrink-0 mb-1">
        {isStreaming ? (
          <button
            onClick={onCancel}
            aria-label="Cancel generating"
            className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-800 flex items-center justify-center transition-colors"
          >
            <Square className="w-5 h-5 fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={isSubmitDisabled}
            aria-label="Send message"
            className={`p-2 rounded-lg flex items-center justify-center transition-colors ${
              isSubmitDisabled 
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed' 
                : 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
            }`}
          >
            <Send className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
};
