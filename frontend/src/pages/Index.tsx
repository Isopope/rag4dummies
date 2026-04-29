import { useState, useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatArea from '@/components/chat/ChatArea';
import ChatInput from '@/components/chat/ChatInput';
import DocumentSidebar from '@/components/chat/DocumentSidebar';
import IngestionPage from '@/components/ingestion/IngestionPage';
import Admin from '@/pages/Admin';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import type { ChatMessage, ChatSession, MessageFeedback, MessageSource } from '@/types/chat';
import type { AppView } from '@/types/layout';
import { useRagQuery } from '@/hooks/use-rag-query';
import { useSessions } from '@/hooks/use-sessions';
import { useIngest } from '@/hooks/use-ingest';
import { useDocuments } from '@/hooks/use-documents';
import { getSession } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { PdfGroundingModal } from '@/components/chat/PdfGroundingModal';

const VIEW_PATHS: Record<AppView, string> = {
  chat: '/chat',
  ingestion: '/ingestion',
  admin: '/admin',
};

function viewFromPath(pathname: string): AppView {
  if (pathname.startsWith('/chat')) return 'chat';
  if (pathname === '/ingestion') return 'ingestion';
  if (pathname === '/admin') return 'admin';
  return 'chat';
}

const Index = () => {
  const { isAdmin, isLoading: isAuthLoading, token } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { conversationId } = useParams<{ conversationId?: string }>();
  const [documentSidebar, setDocumentSidebar] = useState<{
    messageId: string;
    sources: MessageSource[];
  } | null>(null);
  const [viewerSource, setViewerSource] = useState<MessageSource | null>(null);
  const activeView = viewFromPath(location.pathname);
  const isChatView = activeView === 'chat';
  const loadedConversationIdRef = useRef<string | null>(null);
  const previousConversationIdRef = useRef<string | undefined>(conversationId);
  const previousTokenRef = useRef<string | null>(token);

  const { messages, isStreaming, conversationTitle, sessionId, sendMessage, stopGenerating, regenerateMessage, sendFeedback, clearMessages, loadSession } =
    useRagQuery();
  const { sessions, deleteSession: doDelete, renameSession: doRename, refresh: refreshSessions } = useSessions();
  const { files, upload } = useIngest();
  const { documents, deleteDocument: doDeleteDoc } = useDocuments();

  useEffect(() => {
    if (isAuthLoading) return;
    if ((activeView === 'ingestion' || activeView === 'admin') && !isAdmin) {
      navigate(VIEW_PATHS.chat, { replace: true });
    }
  }, [activeView, isAdmin, isAuthLoading, navigate]);

  useEffect(() => {
    const previousToken = previousTokenRef.current;
    previousTokenRef.current = token;

    if (isAuthLoading) return;

    const hasLoggedOut = !!previousToken && !token;
    const hasProtectedConversationUrl = !token && !!conversationId;

    if (!hasLoggedOut && !hasProtectedConversationUrl) return;

    clearMessages();
    setDocumentSidebar(null);
    setViewerSource(null);
    loadedConversationIdRef.current = null;
    previousConversationIdRef.current = undefined;

    if (location.pathname !== VIEW_PATHS.chat || conversationId) {
      navigate(VIEW_PATHS.chat, { replace: true });
    }
  }, [clearMessages, conversationId, isAuthLoading, location.pathname, navigate, token]);

  // -- route → state : charger la conversation indiquée dans l'URL --
  useEffect(() => {
    if (!isChatView) return;
    const previousConversationId = previousConversationIdRef.current;
    previousConversationIdRef.current = conversationId;

    if (!conversationId) {
      loadedConversationIdRef.current = null;
      if (previousConversationId) clearMessages();
      return;
    }
    if (!token) return;
    if (loadedConversationIdRef.current === conversationId) return;

    loadedConversationIdRef.current = conversationId;
    let cancelled = false;

    getSession(conversationId, token)
      .then((detail) => {
        if (cancelled) return;
        loadSession(detail);
      })
      .catch(() => {
        if (cancelled) return;
        loadedConversationIdRef.current = null;
        clearMessages();
        navigate(VIEW_PATHS.chat, { replace: true });
      });

    return () => {
      cancelled = true;
    };
  }, [clearMessages, conversationId, isChatView, loadSession, navigate, token]);

  // -- state → route : donner une vraie URL à une nouvelle conversation --
  useEffect(() => {
    if (!isChatView) return;
    if (conversationId) return;
    if (!sessionId) return;
    navigate(`${VIEW_PATHS.chat}/${sessionId}`, { replace: true });
  }, [conversationId, isChatView, navigate, sessionId]);

  // -- Auto-naming : rafraîchir la liste dès que le LLM a généré un titre --
  // Le titre est déjà persisté en DB (via append_turn dans query.py) quand cet effet se déclenche.
  useEffect(() => {
    if (conversationTitle && sessionId) {
      refreshSessions();
    }
  }, [conversationTitle]); // eslint-disable-line react-hooks/exhaustive-deps

  // ID de la session active
  const activeSessionId = conversationId ?? sessionId ?? null;

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
    (messageId: string, modelId?: string) => {
      regenerateMessage(messageId, modelId);
    },
    [regenerateMessage],
  );

  const handleShowSources = useCallback((message: ChatMessage) => {
    if (!message.sources?.length) return;
    setDocumentSidebar({ messageId: message.id, sources: message.sources });
  }, []);

  const handleNewSession = useCallback(() => {
    clearMessages();
    setDocumentSidebar(null);
    loadedConversationIdRef.current = null;
    navigate(VIEW_PATHS.chat, { replace: true });
  }, [clearMessages, navigate]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === activeSessionId) return;
      clearMessages();
      setDocumentSidebar(null);
      loadedConversationIdRef.current = null;
      navigate(`${VIEW_PATHS.chat}/${id}`);
    },
    [activeSessionId, clearMessages, navigate],
  );

  const handleDeleteSession = useCallback(
    (id: string) => {
      doDelete(id);
      if (id === activeSessionId) {
        clearMessages();
        setDocumentSidebar(null);
        loadedConversationIdRef.current = null;
        navigate(VIEW_PATHS.chat, { replace: true });
      }
    },
    [activeSessionId, clearMessages, doDelete, navigate],
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
        if ((view === 'ingestion' || view === 'admin') && !isAdmin) return;
        const pathname = view === 'chat' && sessionId ? `${VIEW_PATHS.chat}/${sessionId}` : VIEW_PATHS[view];
        if (pathname === location.pathname) return;
        navigate(pathname);
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
          onUpload={(file, entity, validityDate) => upload(file, undefined, undefined, entity, validityDate)}
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
