import { useState, useCallback, useMemo } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatArea from '@/components/chat/ChatArea';
import ChatInput from '@/components/chat/ChatInput';
import DocumentSidebar from '@/components/chat/DocumentSidebar';
import IngestionPage from '@/components/ingestion/IngestionPage';
import Admin from '@/pages/Admin';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import type { ChatMessage, ChatSession, MessageFeedback, MessageSource } from '@/types/chat';
import { useRagQuery } from '@/hooks/use-rag-query';
import { useSessions } from '@/hooks/use-sessions';
import { useIngest } from '@/hooks/use-ingest';
import { useDocuments } from '@/hooks/use-documents';
import { useAuth } from '@/context/AuthContext';
import { PdfGroundingModal } from '@/components/chat/PdfGroundingModal';
import { useIndexRouting } from '@/hooks/use-index-routing';

const Index = () => {
  const { isAdmin, isLoading: isAuthLoading, token } = useAuth();
  const [documentSidebar, setDocumentSidebar] = useState<{
    messageId: string;
    sources: MessageSource[];
  } | null>(null);
  const [viewerSource, setViewerSource] = useState<MessageSource | null>(null);

  const { messages, isStreaming, conversationTitle, sessionId, sendMessage, stopGenerating, regenerateMessage, sendFeedback, clearMessages, loadSession } =
    useRagQuery();
  const { sessions, deleteSession: doDelete, renameSession: doRename, refresh: refreshSessions } = useSessions();
  const { files, upload } = useIngest();
  const {
    documents,
    stats: documentStats,
    total: documentsTotal,
    pageIndex: documentsPageIndex,
    pageCount: documentsPageCount,
    pageSize: documentsPageSize,
    isFetching: isDocumentsFetching,
    setPageIndex: setDocumentsPageIndex,
    setPageSize: setDocumentsPageSize,
    deleteDocument: doDeleteDoc,
  } = useDocuments();

  const resetPanels = useCallback(() => {
    setDocumentSidebar(null);
    setViewerSource(null);
  }, []);

  const {
    activeView,
    activeSessionId,
    navigateToView,
    startNewSession,
    openSession,
  } = useIndexRouting({
    isAdmin,
    isAuthLoading,
    token,
    sessionId,
    conversationTitle,
    clearMessages,
    loadSession,
    refreshSessions,
    resetPanels,
  });

  const displayedSessions: ChatSession[] = useMemo(() => {
    return sessions.map((session) => {
      const isActiveUntitledSession =
        session.id === activeSessionId &&
        !!conversationTitle &&
        session.title !== conversationTitle;

      return {
        id: session.id,
        title: isActiveUntitledSession ? conversationTitle : (session.title ?? 'Conversation sans titre'),
        lastMessage: session.last_message ?? '',
        timestamp: new Date(session.updated_at),
        messageCount: session.message_count,
      };
    });
  }, [activeSessionId, conversationTitle, sessions]);

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
    (messageId: string, modelId?: string) => {
      regenerateMessage(messageId, modelId);
    },
    [regenerateMessage],
  );

  const handleShowSources = useCallback((message: ChatMessage) => {
    if (!message.sources?.length) return;
    setDocumentSidebar({ messageId: message.id, sources: message.sources });
  }, []);

  const handleDeleteSession = useCallback(
    (id: string) => {
      doDelete(id);
      if (id === activeSessionId) {
        startNewSession();
      }
    },
    [activeSessionId, doDelete, startNewSession],
  );

  const handleRenameSession = useCallback(
    (id: string, title: string) => {
      doRename(id, title);
    },
    [doRename],
  );

  return (
    <AppLayout
      activeView={activeView}
      onViewChange={navigateToView}
      sidebar={
        <ChatSidebar
          sessions={displayedSessions}
          activeSessionId={activeSessionId ?? ''}
          onSelectSession={openSession}
          onNewSession={startNewSession}
          onDeleteSession={handleDeleteSession}
          onRenameSession={handleRenameSession}
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
              onOpenViewer={(source) => setViewerSource(source)}
            />
            <ChatInput
              onSend={handleSend}
              disabled={false}
              isStreaming={isStreaming}
              onStopGenerating={stopGenerating}
            />
          </div>

          {/* Document sidebar */}
          {documentSidebar && (
            <div className="hidden w-80 shrink-0 border-l border-border lg:block animate-slide-in-left">
              <DocumentSidebar
                messageId={documentSidebar.messageId}
                sources={documentSidebar.sources}
                onClose={() => setDocumentSidebar(null)}
                onOpenViewer={(source) => setViewerSource(source)}
              />
            </div>
          )}
        </div>
      ) : activeView === 'ingestion' ? (
        <IngestionPage
          uploadingFiles={files}
          documents={documents}
          documentStats={documentStats}
          documentsTotal={documentsTotal}
          documentsPageIndex={documentsPageIndex}
          documentsPageCount={documentsPageCount}
          documentsPageSize={documentsPageSize}
          isDocumentsFetching={isDocumentsFetching}
          onDocumentsPageChange={setDocumentsPageIndex}
          onDocumentsPageSizeChange={setDocumentsPageSize}
          onUpload={(file, entity, validityDate) => upload(file, entity, validityDate)}
          onDeleteDocument={doDeleteDoc}
        />
      ) : (
        <Admin />
      )}
      
      <PdfGroundingModal 
        source={viewerSource} 
        onClose={() => setViewerSource(null)} 
      />
    </AppLayout>
  );
};

export default Index;
