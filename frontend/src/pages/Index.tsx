import { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatArea from '@/components/chat/ChatArea';
import ChatInput from '@/components/chat/ChatInput';
import DocumentSidebar from '@/components/chat/DocumentSidebar';
import IngestionPage from '@/components/ingestion/IngestionPage';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import type { ChatMessage, ChatSession, MessageFeedback, MessageSource } from '@/types/chat';
import { useRagQuery } from '@/hooks/use-rag-query';
import { useSessions } from '@/hooks/use-sessions';
import { useIngest } from '@/hooks/use-ingest';
import { useDocuments } from '@/hooks/use-documents';
import { getSession } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';

const CHAT_ID_PARAM = 'chat-id';

const Index = () => {
  const { isAdmin, token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeView, setActiveView] = useState<'chat' | 'ingestion'>('chat');
  const [documentSidebar, setDocumentSidebar] = useState<{
    messageId: string;
    sources: MessageSource[];
  } | null>(null);

  const { messages, isStreaming, conversationTitle, sessionId, sendMessage, sendFeedback, clearMessages, loadSession } =
    useRagQuery();
  const { sessions, deleteSession: doDelete, renameSession: doRename, refresh: refreshSessions } = useSessions();
  const { files, upload } = useIngest();
  const { documents, deleteDocument: doDeleteDoc } = useDocuments();

  // -- URL → state : charger la session indiquée dans l'URL au montage (ou au changement de param) --
  const initialLoadDone = useRef(false);
  useEffect(() => {
    const urlChatId = searchParams.get(CHAT_ID_PARAM);
    if (!urlChatId) return;
    // Évite de recharger si la session est déjà active
    if (urlChatId === sessionId) return;
    // Évite le double-chargement au montage strict-mode
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    getSession(urlChatId, token!)
      .then((detail) => loadSession(detail))
      .catch(() => {
        // Session invalide ou supprimée → nettoyer l'URL
        setSearchParams((prev) => {
          prev.delete(CHAT_ID_PARAM);
          return prev;
        }, { replace: true });
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionnellement déclenché uniquement au montage

  // -- state → URL : synchroniser l'URL quand sessionId est assigné ou change --
  useEffect(() => {
    if (!sessionId) return;
    if (searchParams.get(CHAT_ID_PARAM) === sessionId) return;
    setSearchParams({ [CHAT_ID_PARAM]: sessionId }, { replace: true });
  }, [sessionId, searchParams, setSearchParams]);

  // -- Auto-naming : rafraîchir la liste dès que le LLM a généré un titre --
  // Le titre est déjà persisté en DB (via append_turn dans query.py) quand cet effet se déclenche.
  useEffect(() => {
    if (conversationTitle && sessionId) {
      refreshSessions();
    }
  }, [conversationTitle]); // eslint-disable-line react-hooks/exhaustive-deps

  // ID de la session active
  const activeSessionId = sessionId ?? null;

  // Sessions formatées pour ChatSidebar (type ChatSession)
  const displayedSessions: ChatSession[] = sessions.map((s) => ({
    id: s.id,
    title: s.title ?? 'Conversation sans titre',
    lastMessage: s.last_message ?? '',
    timestamp: new Date(s.updated_at),
    messageCount: s.message_count,
  }));

  // Met à jour le titre dans la sidebar quand le LLM le génère
  if (activeSessionId && conversationTitle) {
    const idx = displayedSessions.findIndex((s) => s.id === activeSessionId);
    if (idx >= 0 && displayedSessions[idx].title !== conversationTitle) {
      displayedSessions[idx] = { ...displayedSessions[idx], title: conversationTitle };
    }
  }

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

  const handleNewSession = useCallback(() => {
    clearMessages();
    setDocumentSidebar(null);
    // Supprime le param URL → nouvelle conversation sans identifiant
    setSearchParams((prev) => {
      prev.delete(CHAT_ID_PARAM);
      return prev;
    }, { replace: true });
    initialLoadDone.current = false;
  }, [clearMessages, setSearchParams]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      if (id === activeSessionId) return;
      try {
        const detail = await getSession(id, token!);
        loadSession(detail);
        setDocumentSidebar(null);
        refreshSessions();
        // L'URL sera mise à jour via le useEffect ci-dessus quand sessionId change
      } catch {
        clearMessages();
        setDocumentSidebar(null);
        setSearchParams((prev) => {
          prev.delete(CHAT_ID_PARAM);
          return prev;
        }, { replace: true });
      }
    },
    [activeSessionId, clearMessages, loadSession, refreshSessions, setSearchParams],
  );

  const handleDeleteSession = useCallback(
    (id: string) => {
      doDelete(id);
      if (id === activeSessionId) {
        clearMessages();
        setDocumentSidebar(null);
        setSearchParams((prev) => {
          prev.delete(CHAT_ID_PARAM);
          return prev;
        }, { replace: true });
      }
    },
    [activeSessionId, clearMessages, doDelete, setSearchParams],
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
      onViewChange={(view) => {
        // Seuls les admins peuvent accéder à la vue ingestion
        if (view === 'ingestion' && !isAdmin) return;
        setActiveView(view);
      }}
      sidebar={
        <ChatSidebar
          sessions={displayedSessions}
          activeSessionId={activeSessionId ?? ''}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
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
          uploadingFiles={files}
          documents={documents}
          onUpload={upload}
          onDeleteDocument={doDeleteDoc}
        />
      )}
    </AppLayout>
  );
};

export default Index;
