import { useState, useCallback } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatArea from '@/components/chat/ChatArea';
import ChatInput from '@/components/chat/ChatInput';
import DocumentSidebar from '@/components/chat/DocumentSidebar';
import IngestionPage from '@/components/ingestion/IngestionPage';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import type { ChatMessage, ChatSession, MessageFeedback, MessageSource } from '@/types/chat';
import { useRagQuery } from '@/hooks/use-rag-query';
import { useIngest } from '@/hooks/use-ingest';
import { useSources } from '@/hooks/use-sources';
import { mockConnectors } from '@/data/mockData';

const INITIAL_SESSION: ChatSession = {
  id: 'session-1',
  title: 'Nouvelle conversation',
  lastMessage: '',
  timestamp: new Date(),
  messageCount: 0,
};

const Index = () => {
  const [activeView, setActiveView] = useState<'chat' | 'ingestion'>('chat');
  const [sessions, setSessions] = useState<ChatSession[]>([INITIAL_SESSION]);
  const [activeSessionId, setActiveSessionId] = useState('session-1');
  const [documentSidebar, setDocumentSidebar] = useState<{
    messageId: string;
    sources: MessageSource[];
  } | null>(null);

  const { messages, isStreaming, conversationTitle, sendMessage, sendFeedback, clearMessages } =
    useRagQuery();
  const { files, upload } = useIngest();
  const { data: sourcesData } = useSources();

  const handleSend = useCallback(
    (payload: ChatInputSubmitPayload | string) => {
      sendMessage(payload);
    },
    [sendMessage],
  );

  const handleFeedback = useCallback(
    (messageId: string, feedback: MessageFeedback) => {
      sendFeedback(messageId, feedback);
    },
    [sendFeedback],
  );

  const handleRegenerate = useCallback(
    (messageId: string) => {
      const idx = messages.findIndex((m) => m.id === messageId);
      if (idx <= 0) return;
      const questionMsg = messages[idx - 1];
      if (questionMsg.role !== 'user') return;
      const text = questionMsg.contents.find((c) => c.type === 'text')?.text;
      if (text) sendMessage(text);
    },
    [messages, sendMessage],
  );

  const handleShowSources = useCallback((message: ChatMessage) => {
    if (!message.sources?.length) return;
    setDocumentSidebar({ messageId: message.id, sources: message.sources });
  }, []);

  const snapshotCurrentSession = useCallback(
    (prev: ChatSession[]): ChatSession[] => {
      const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
      return prev.map((s) =>
        s.id === activeSessionId
          ? {
              ...s,
              title: conversationTitle ?? s.title,
              lastMessage:
                lastAssistant?.contents.find((c) => c.type === 'text')?.text?.slice(0, 60) ??
                s.lastMessage,
              messageCount: messages.length,
            }
          : s,
      );
    },
    [activeSessionId, conversationTitle, messages],
  );

  const handleNewSession = useCallback(() => {
    const id = `session-${Date.now()}`;
    setSessions((prev) => [
      { id, title: 'Nouvelle conversation', lastMessage: '', timestamp: new Date(), messageCount: 0 },
      ...snapshotCurrentSession(prev),
    ]);
    setActiveSessionId(id);
    clearMessages();
    setDocumentSidebar(null);
  }, [clearMessages, snapshotCurrentSession]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === activeSessionId) return;
      setSessions((prev) => snapshotCurrentSession(prev));
      setActiveSessionId(id);
      clearMessages();
      setDocumentSidebar(null);
    },
    [activeSessionId, clearMessages, snapshotCurrentSession],
  );

  const displayedSessions = sessions.map((s) =>
    s.id === activeSessionId && conversationTitle
      ? { ...s, title: conversationTitle, messageCount: messages.length }
      : s,
  );

  return (
    <AppLayout
      activeView={activeView}
      onViewChange={setActiveView}
      sidebar={
        <ChatSidebar
          sessions={displayedSessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
        />
      }
    >
      {activeView === 'chat' ? (
        <div className="flex h-full min-w-0">
          {/* Main chat column */}
          <div className="flex flex-col flex-1 min-w-0">
            <ChatArea
              messages={messages}
              isTyping={isStreaming}
              onSelectSuggestion={handleSend}
              onFeedback={handleFeedback}
              onRegenerate={handleRegenerate}
              onShowSources={handleShowSources}
            />
            <ChatInput
              onSend={handleSend}
              disabled={false}
              isStreaming={isStreaming}
            />
          </div>

          {/* Document sidebar */}
          {documentSidebar && (
            <div className="hidden w-80 shrink-0 border-l border-border lg:block animate-slide-in-left">
              <DocumentSidebar
                messageId={documentSidebar.messageId}
                sources={documentSidebar.sources}
                onClose={() => setDocumentSidebar(null)}
              />
            </div>
          )}
        </div>
      ) : (
        <IngestionPage
          connectors={mockConnectors}
          files={files}
          onUpload={upload}
          totalIndexedChunks={sourcesData?.total_chunks ?? 0}
        />
      )}
    </AppLayout>
  );
};

export default Index;
