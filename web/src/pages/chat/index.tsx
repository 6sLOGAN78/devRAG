import React, { useState, useEffect, useRef } from 'react';
import { useChatSessions, useCreateChatSession, useChatHistory } from '../../hooks/use-chat';
import type { ChatMessage as IChatMessage } from '../../hooks/use-chat';
import { useSendMessage } from '../../hooks/use-send-message';
import { MessageInput } from '../../components/message-input';
import { MessageSquare, Plus, Loader2, User, Bot, AlertCircle } from 'lucide-react';

const ChatBubble = ({ message, isStreaming }: { message: IChatMessage; isStreaming?: boolean }) => {
  const isUser = message.role === 'user';
  
  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      <div className={`flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-4`}>
        <div className="flex-shrink-0 mt-1">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${isUser ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'}`}>
            {isUser ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
          </div>
        </div>
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <span className="text-sm text-gray-500 mb-1 px-1">
            {isUser ? 'You' : 'Assistant'}
          </span>
          <div className={`p-4 rounded-2xl ${isUser ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-gray-100 text-gray-800 rounded-tl-none'} shadow-sm whitespace-pre-wrap break-words`}>
            {message.content}
            {isStreaming && <span className="ml-1 animate-pulse inline-block w-2 h-4 bg-gray-500 align-middle"></span>}
          </div>
        </div>
      </div>
    </div>
  );
};

export const ChatPage = () => {
  const { data: sessions, isLoading: isLoadingSessions } = useChatSessions();
  const createSession = useCreateChatSession();
  
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  
  const { data: history, isLoading: isLoadingHistory, error: historyError } = useChatHistory(activeSessionId);
  const { sendMessage, isStreaming, streamingMessage, error: streamError, cancel } = useSendMessage({ 
    sessionId: activeSessionId || '' 
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Default select first session
  useEffect(() => {
    if (sessions && sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  // Handle scroll to bottom
  const scrollToBottom = () => {
    if (scrollRef.current && autoScroll) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [history, streamingMessage]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    const isNearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 50;
    setAutoScroll(isNearBottom);
  };

  const handleNewChat = async () => {
    try {
      const newSession = await createSession.mutateAsync({
        agent_id: 'default-canvas',
        title: 'New Conversation'
      });
      setActiveSessionId(newSession.id);
    } catch (e) {
      console.error("Failed to create chat session", e);
    }
  };

  return (
    <div className="flex h-full w-full bg-white rounded-lg border shadow-sm overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-50 border-r flex flex-col hidden md:flex">
        <div className="p-4 border-b">
          <button 
            onClick={handleNewChat}
            disabled={createSession.isPending}
            className="w-full flex items-center justify-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            {createSession.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            <span>New Chat</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoadingSessions ? (
            <div className="p-4 text-center text-sm text-gray-500">Loading sessions...</div>
          ) : sessions?.length === 0 ? (
            <div className="p-4 text-center text-sm text-gray-500">No chats yet</div>
          ) : (
            sessions?.map(session => (
              <button
                key={session.id}
                onClick={() => setActiveSessionId(session.id)}
                className={`w-full text-left px-3 py-3 rounded-lg flex items-center space-x-3 transition-colors ${
                  activeSessionId === session.id ? 'bg-blue-100 text-blue-900' : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <MessageSquare className="w-4 h-4 flex-shrink-0" />
                <span className="truncate text-sm font-medium">{session.title || 'Untitled Chat'}</span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col bg-white min-w-0">
        {!activeSessionId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500">
            <MessageSquare className="w-12 h-12 mb-4 text-gray-300" />
            <h2 className="text-xl font-medium mb-2">Select a Conversation</h2>
            <p className="text-sm">Choose an existing chat from the sidebar or start a new one.</p>
          </div>
        ) : (
          <>
            {/* Header (Mobile-friendly toggle could go here) */}
            <header className="h-14 border-b flex items-center px-6">
              <h2 className="font-medium text-gray-800 truncate">
                {sessions?.find(s => s.id === activeSessionId)?.title || 'Chat'}
              </h2>
            </header>

            {/* Messages Area */}
            <div 
              ref={scrollRef}
              onScroll={handleScroll}
              className="flex-1 overflow-y-auto p-6"
            >
              {isLoadingHistory ? (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <Loader2 className="w-8 h-8 animate-spin" />
                </div>
              ) : historyError ? (
                <div className="flex flex-col items-center justify-center h-full text-red-500">
                  <AlertCircle className="w-8 h-8 mb-2" />
                  <p>Unable to load conversation.</p>
                </div>
              ) : history?.length === 0 && !isStreaming ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-500">
                  <Bot className="w-12 h-12 mb-4 text-gray-300" />
                  <h3 className="text-lg font-medium mb-1">Start chatting</h3>
                  <p className="text-sm">Send a message to begin the conversation.</p>
                </div>
              ) : (
                <div className="max-w-4xl mx-auto w-full flex flex-col">
                  {history?.map(msg => (
                    <ChatBubble key={msg.id} message={msg} />
                  ))}
                  
                  {isStreaming && (
                    <ChatBubble 
                      message={{
                        id: 'streaming-temp',
                        session_id: activeSessionId,
                        tenant_id: '',
                        role: 'assistant',
                        content: streamingMessage || '...',
                        citations: null,
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString()
                      }} 
                      isStreaming={true}
                    />
                  )}
                  
                  {streamError && (
                    <div className="flex items-center space-x-2 text-red-600 bg-red-50 p-3 rounded-lg mx-auto max-w-xl my-4 text-sm">
                      <AlertCircle className="w-5 h-5 flex-shrink-0" />
                      <span>{streamError}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Input Area */}
            <div className="p-4 border-t bg-gray-50">
              <MessageInput 
                onSend={sendMessage}
                onCancel={cancel}
                isStreaming={isStreaming}
                disabled={!activeSessionId || isLoadingHistory}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
};
