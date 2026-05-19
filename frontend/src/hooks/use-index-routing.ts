import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { getSession, type SessionDetail } from '@/lib/api';
import { buildChatPath, buildViewPath, VIEW_PATHS, viewFromPath } from '@/lib/app-routes';
import type { AppView } from '@/types/layout';

interface UseIndexRoutingArgs {
  isAdmin: boolean;
  isAuthLoading: boolean;
  token: string | null;
  sessionId?: string;
  conversationTitle?: string;
  clearMessages: () => void;
  loadSession: (detail: SessionDetail) => void;
  refreshSessions: () => void;
  resetPanels: () => void;
}

export function useIndexRouting({
  isAdmin,
  isAuthLoading,
  token,
  sessionId,
  conversationTitle,
  clearMessages,
  loadSession,
  refreshSessions,
  resetPanels,
}: UseIndexRoutingArgs) {
  const location = useLocation();
  const navigate = useNavigate();
  const { conversationId } = useParams<{ conversationId?: string }>();
  const activeView = useMemo(() => viewFromPath(location.pathname), [location.pathname]);
  const isChatView = activeView === 'chat';
  const loadedConversationIdRef = useRef<string | null>(null);
  const previousConversationIdRef = useRef<string | undefined>(conversationId);
  const previousTokenRef = useRef<string | null>(token);

  const resetConversationState = useCallback(() => {
    clearMessages();
    resetPanels();
    loadedConversationIdRef.current = null;
    previousConversationIdRef.current = undefined;
  }, [clearMessages, resetPanels]);

  const goToChatHome = useCallback(() => {
    navigate(VIEW_PATHS.chat, { replace: true });
  }, [navigate]);

  useEffect(() => {
    if (isAuthLoading) return;
    if ((activeView === 'ingestion' || activeView === 'admin') && !isAdmin) {
      goToChatHome();
    }
  }, [activeView, goToChatHome, isAdmin, isAuthLoading]);

  useEffect(() => {
    const previousToken = previousTokenRef.current;
    previousTokenRef.current = token;

    if (isAuthLoading) return;

    const hasLoggedOut = !!previousToken && !token;
    const hasProtectedConversationUrl = !token && !!conversationId;

    if (!hasLoggedOut && !hasProtectedConversationUrl) return;

    resetConversationState();

    if (location.pathname !== VIEW_PATHS.chat || conversationId) {
      goToChatHome();
    }
  }, [conversationId, goToChatHome, isAuthLoading, location.pathname, resetConversationState, token]);

  useEffect(() => {
    if (!isChatView) return;

    const previousConversationId = previousConversationIdRef.current;
    previousConversationIdRef.current = conversationId;

    if (!conversationId) {
      loadedConversationIdRef.current = null;
      if (previousConversationId) {
        resetConversationState();
      }
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
        resetConversationState();
        goToChatHome();
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId, goToChatHome, isChatView, loadSession, resetConversationState, token]);

  useEffect(() => {
    if (!isChatView) return;
    if (conversationId) return;
    if (!sessionId) return;

    loadedConversationIdRef.current = sessionId;
    navigate(buildChatPath(sessionId), { replace: true });
  }, [conversationId, isChatView, navigate, sessionId]);

  useEffect(() => {
    if (conversationTitle && sessionId) {
      refreshSessions();
    }
  }, [conversationTitle, refreshSessions, sessionId]);

  const activeSessionId = conversationId ?? sessionId ?? null;

  const navigateToView = useCallback(
    (view: AppView) => {
      if ((view === 'ingestion' || view === 'admin') && !isAdmin) return;
      const nextPath = buildViewPath(view, sessionId);
      if (nextPath === location.pathname) return;
      navigate(nextPath);
    },
    [isAdmin, location.pathname, navigate, sessionId],
  );

  const startNewSession = useCallback(() => {
    resetConversationState();
    goToChatHome();
  }, [goToChatHome, resetConversationState]);

  const openSession = useCallback(
    (id: string) => {
      if (id === activeSessionId) return;
      resetConversationState();
      navigate(buildChatPath(id));
    },
    [activeSessionId, navigate, resetConversationState],
  );

  return {
    activeView,
    activeSessionId,
    navigateToView,
    startNewSession,
    openSession,
    resetConversationState,
    goToChatHome,
  };
}
