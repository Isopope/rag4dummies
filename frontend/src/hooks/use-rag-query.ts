import { useState, useCallback, useRef, useEffect } from 'react';
import { streamQueryRAG, submitFeedback } from '@/lib/api';
import type { ChunkModel, CitationInfoModel, FeedbackPayload, SessionDetail, TokenUsageSummary } from '@/lib/api';
import type {
  ChatMessage,
  MessageFeedback,
  MessageSource,
  AgentStep,
  MessageFeedbackContext,
} from '@/types/chat';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import { IDLE_CHAT_RUN_STATE, resolveSessionSaveStatus, type ChatRunState } from '@/lib/workflow-state';

function chunkToSource(c: ChunkModel): MessageSource {
  return {
    id: `${c.source}-${c.chunk_index}`,
    title: c.source.split('/').pop() ?? c.source,
    excerpt: c.page_content.slice(0, 200),
    url: c.pdf_url,
    bboxes: c.bboxes,
    pageIdx: c.page_idx,
    kind: c.kind,
  };
}

/** Builds a map citation_number → MessageSource from the citation_infos + raw chunks. */
function buildCitationSources(
  citationInfos: CitationInfoModel[],
  chunks: ChunkModel[],
): Record<number, MessageSource> {
  const map: Record<number, MessageSource> = {};
  for (const cit of citationInfos) {
    // Prefer the chunk that matches both source path AND page_idx (exact bbox match)
    const chunk =
      chunks.find((c) => c.source === cit.source && c.page_idx === cit.page_idx) ??
      chunks.find((c) => c.source === cit.source);
    if (chunk) {
      map[cit.citation_number] = {
        id: `citation-${cit.citation_number}`,
        title: cit.title_path || (cit.source.split('/').pop() ?? cit.source),
        url: chunk.pdf_url,
        bboxes: chunk.bboxes,
        pageIdx: cit.page_idx,
        kind: chunk.kind,
      };
    }
  }
  return map;
}

function buildSummary(messages: ChatMessage[]): string {
  return messages
    .slice(-6)
    .map((m) => {
      const text = m.contents.find((c) => c.type === 'text')?.text ?? '';
      return `${m.role === 'user' ? 'Utilisateur' : 'Assistant'}: ${text.slice(0, 500)}`;
    })
    .join('\n');
}

function getMessageText(message: ChatMessage): string {
  return message.contents
    .map((content) => {
      if (content.type === 'text') return content.text ?? '';
      if (content.type === 'code') return content.code ?? '';
      if (content.type === 'json') return JSON.stringify(content.jsonData, null, 2);
      return '';
    })
    .filter(Boolean)
    .join('\n\n')
    .trim();
}

function getFeedbackContextForMessage(
  messages: ChatMessage[],
  messageId: string,
): MessageFeedbackContext | null {
  const messageIndex = messages.findIndex((message) => message.id === messageId);
  if (messageIndex === -1) return null;

  const message = messages[messageIndex];
  if (message.role !== 'assistant') return null;
  if (message.feedbackContext) return message.feedbackContext;

  const previousUser = messages
    .slice(0, messageIndex)
    .reverse()
    .find((candidate) => candidate.role === 'user');
  const question = previousUser ? getMessageText(previousUser) : '';
  const answer = getMessageText(message);

  if (!question || !answer) return null;

  return {
    question,
    answer,
    followUps: message.followUpSuggestions,
    nRetrieved: message.sources?.length ?? 0,
  };
}

/** Human-readable labels for agent graph nodes */
const NODE_LABELS: Record<string, string> = {
  analyze_and_plan: '📋 Analyse & planification',
  agent_reason: '🤔 Raisonnement',
  agent_action: '🔍 Recherche documentaire',
  compress_context: '🗜️ Compression du contexte',
  consolidate_chunks: '📦 Consolidation des résultats',
  rerank_prep: '📊 Préparation du classement',
  rerank: '📊 Re-classement des résultats',
  generate: '✍️ Génération de la réponse',
  generate_follow_up: '❓ Suggestions de suivi',
  generate_title: '📝 Titre de conversation',
};

function nodeLabel(node: string): string {
  return NODE_LABELS[node] ?? `⚙️ ${node.replace(/_/g, ' ')}`;
}

export function useRagQuery() {
  const { token, isAuthenticated } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationTitle, setConversationTitle] = useState<string | undefined>();
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [runState, setRunState] = useState<ChatRunState>(IDLE_CHAT_RUN_STATE);
  const abortRef = useRef<AbortController | null>(null);
  // Always-current refs so callbacks don't need state in dep array
  const messagesRef = useRef<ChatMessage[]>([]);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const sessionIdRef = useRef<string | undefined>();
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  /** Core streaming executor — shared by sendMessage and regenerateMessage. */
  const _executeStream = useCallback(async (
    text: string,
    modelId: string | undefined,
    assistantId: string,
    /** Called once with the placeholder before streaming starts; sets messages. */
    initMessages: (placeholder: ChatMessage) => void,
  ) => {
    const controller = new AbortController();
    abortRef.current = controller;

    const conversationSummary = buildSummary(messagesRef.current);
    const currentSessionId = sessionIdRef.current;

    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      contents: [{ type: 'text', text: '' }],
      timestamp: new Date(),
      isStreaming: true,
      lifecycleStatus: 'streaming',
      steps: [],
    };

    initMessages(assistantPlaceholder);
    setIsStreaming(true);
    setRunState({
      status: 'starting',
      sessionSaveStatus: 'idle',
      warnings: [],
      activeAssistantId: assistantId,
    });

    let accText = '';
    let finalSources: ChunkModel[] = [];
    let finalCitationInfos: CitationInfoModel[] = [];
    let finalFollowUps: string[] = [];
    let finalTitle: string | undefined;
    let finalQuestionId: string | undefined;
    let finalUsage: TokenUsageSummary | undefined;
    let finalWarnings: string[] = [];
    let finalSessionSaved: boolean | undefined;
    let hasStreamStarted = false;
    const steps: AgentStep[] = [];

    try {
      for await (const event of streamQueryRAG(
        { question: text, conversation_summary: conversationSummary, session_id: currentSessionId, model: modelId },
        controller.signal,
        token,
      )) {
        if (!hasStreamStarted) {
          hasStreamStarted = true;
          setRunState((prev) => ({ ...prev, status: 'streaming' }));
        }
        if (event.type === 'node_update' && event.node) {
          const prev = steps.find((s) => s.status === 'running');
          if (prev) prev.status = 'done';
          steps.push({
            node: event.node,
            message: event.message || nodeLabel(event.node),
            timestamp: new Date(),
            status: 'running',
          });
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, steps: [...steps] } : m),
          );
        } else if (event.type === 'answer' && event.answer != null) {
          accText = event.answer;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, contents: [{ type: 'text', text: accText }], steps: [...steps] }
                : m,
            ),
          );
        } else if (event.type === 'done') {
          if (event.answer != null) accText = event.answer;
          finalSources        = event.sources ?? [];
          finalCitationInfos  = event.citation_infos ?? [];
          finalFollowUps      = event.follow_up_suggestions ?? [];
          finalTitle          = event.conversation_title;
          finalQuestionId     = event.question_id;
          finalSessionSaved   = event.session_saved;
          finalWarnings       = event.warnings ?? [];
          finalUsage          = event.usage;
          if (event.session_id) setSessionId(event.session_id);
        } else if (event.type === 'error') {
          throw new Error(event.error ?? 'Erreur SSE');
        }
      }

      steps.forEach((s) => { s.status = 'done'; });
      if (finalTitle) setConversationTitle(finalTitle);
      if (finalWarnings.length > 0) {
        toast.warning(finalWarnings[0]);
      }

      const sessionSaveStatus = resolveSessionSaveStatus(finalSessionSaved, isAuthenticated);
      const lifecycleStatus =
        finalWarnings.length > 0 || sessionSaveStatus === 'save_failed' ? 'degraded' : 'completed';

      setRunState({
        status: lifecycleStatus,
        sessionSaveStatus,
        warnings: finalWarnings,
        activeAssistantId: assistantId,
      });

      const feedbackContext: MessageFeedbackContext = {
        questionId: finalQuestionId || undefined,
        question: text,
        answer: accText,
        sources: finalSources,
        followUps: finalFollowUps,
        title: finalTitle,
        nRetrieved: finalSources.length,
        usage: finalUsage,
      };

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                contents: [{ type: 'text', text: accText }],
                isStreaming: false,
                lifecycleStatus,
                sources: finalSources.length ? finalSources.map(chunkToSource) : undefined,
                citationSources: finalCitationInfos.length
                  ? buildCitationSources(finalCitationInfos, finalSources)
                  : undefined,
                followUpSuggestions: finalFollowUps.length ? finalFollowUps : undefined,
                warnings: finalWarnings.length ? finalWarnings : undefined,
                steps: [...steps],
                feedbackContext,
              }
            : m,
        ),
      );
    } catch (err) {
      steps.forEach((s) => { s.status = 'done'; });
      if ((err as Error).name === 'AbortError') {
        setRunState({
          status: 'cancelled',
          sessionSaveStatus: resolveSessionSaveStatus(undefined, isAuthenticated),
          warnings: [],
          activeAssistantId: assistantId,
        });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  contents: [{ type: 'text', text: accText || 'Génération interrompue.' }],
                  isStreaming: false,
                  lifecycleStatus: 'cancelled',
                  steps: [...steps],
                }
              : m,
          ),
        );
        return;
      }
      const msg = err instanceof Error ? err.message : 'Erreur de connexion';
      toast.error(`Erreur : ${msg}`);
      setRunState({
        status: 'failed',
        sessionSaveStatus: resolveSessionSaveStatus(undefined, isAuthenticated),
        warnings: [],
        activeAssistantId: assistantId,
        error: msg,
      });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                contents: [{ type: 'text', text: `❌ ${msg}` }],
                isStreaming: false,
                lifecycleStatus: 'failed',
                steps: [...steps],
              }
            : m,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  }, [isAuthenticated, token]);

  const sendMessage = useCallback(async (payload: ChatInputSubmitPayload | string) => {
    const text = typeof payload === 'string' ? payload : payload.text;
    const modelId = typeof payload === 'string' ? undefined : payload.modelId || undefined;
    if (!text.trim()) return;

    abortRef.current?.abort();

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      contents: [{ type: 'text', text }],
      timestamp: new Date(),
    };

    const assistantId = `a-${Date.now() + 1}`;
    await _executeStream(text, modelId, assistantId, (placeholder) =>
      setMessages((prev) => [...prev, userMsg, placeholder]),
    );
  }, [_executeStream]);

  /** Stop any in-progress generation. */
  const stopGenerating = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  /**
   * Re-run the query for an existing assistant message, optionally with a different model.
   * Allowed only for the latest assistant response to avoid invalidating later turns.
   */
  const regenerateMessage = useCallback(async (assistantMsgId: string, modelId?: string) => {
    const msgs = messagesRef.current;
    const idx = msgs.findIndex((m) => m.id === assistantMsgId);
    if (idx <= 0) return;
    if (idx !== msgs.length - 1) {
      toast.error("La regeneration n'est disponible que pour la derniere reponse.");
      return;
    }
    const userMsg = msgs[idx - 1];
    if (userMsg.role !== 'user') return;
    const text = userMsg.contents.find((c) => c.type === 'text')?.text ?? '';
    if (!text.trim()) return;

    abortRef.current?.abort();

    // Remove the old assistant response (and everything after) so the user bubble stays
    const truncated = msgs.slice(0, idx);
    messagesRef.current = truncated;
    setMessages(truncated);

    const assistantId = `a-${Date.now()}`;
    await _executeStream(text, modelId, assistantId, (placeholder) =>
      setMessages((prev) => [...prev, placeholder]),
    );
  }, [_executeStream]);

  const sendFeedback = useCallback(async (messageId: string, feedback: MessageFeedback) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, feedback } : m)));
    const context = getFeedbackContextForMessage(messagesRef.current, messageId);
    if (!context) {
      toast.error("Impossible de retrouver le contexte de cette reponse.");
      return;
    }
    try {
      const payload: FeedbackPayload = {
        question_id: context.questionId,
        question: context.question,
        answer: context.answer,
        rating: feedback.vote === 'up' ? 5 : 1,
        comment: feedback.explanation,
        conversation_title: context.title,
        sources: context.sources,
        follow_up_suggestions: context.followUps,
        n_retrieved: context.nRetrieved,
        usage: context.usage,
      };
      await submitFeedback(payload);
      toast.success(feedback.vote === 'up' ? 'Merci pour votre retour !' : 'Retour enregistré.');
    } catch {
      toast.error("Impossible d'enregistrer le feedback.");
    }
  }, []);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    setConversationTitle(undefined);
    setSessionId(undefined);
    setRunState(IDLE_CHAT_RUN_STATE);
    messagesRef.current = [];
  }, []);

  /** Restaure une session depuis l'historique (appel à GET /sessions/{id}). */
  const loadSession = useCallback((detail: SessionDetail) => {
    abortRef.current?.abort();
    setSessionId(detail.id);
    setConversationTitle(detail.title ?? undefined);
    setRunState(IDLE_CHAT_RUN_STATE);

    const restored: ChatMessage[] = [];
    for (const m of detail.messages) {
      if (m.role === 'user') {
        restored.push({
          id: m.id,
          role: 'user',
          contents: [{ type: 'text', text: m.content }],
          timestamp: new Date(m.created_at),
        });
      } else {
        const previousUser = restored
          .slice()
          .reverse()
          .find((candidate) => candidate.role === 'user');
        const sources: MessageSource[] = m.sources.map((c) => ({
          id: `${c.source}-${c.chunk_index}`,
          title: c.source.split('/').pop() ?? c.source,
          excerpt: c.page_content.slice(0, 200),
          url: c.pdf_url,
          bboxes: c.bboxes,
          pageIdx: c.page_idx,
          kind: c.kind,
        }));

        // Reconstruct citationSources mapping from sources
        const citationSources: Record<number, MessageSource> = {};
        sources.forEach((src, idx) => {
          citationSources[idx + 1] = src;
        });

        // Hyperlink citations in m.content on the fly!
        let contentText = m.content;
        sources.forEach((src, idx) => {
          const n = idx + 1;
          if (src.url) {
            const escapedUrl = src.url.replace(/\$/g, '$$$$');
            const regex = new RegExp(`\\[${n}\\](?!\\]\\()`, 'g');
            contentText = contentText.replace(regex, `[[${n}]](${escapedUrl})`);
          }
        });

        restored.push({
          id: m.id,
          role: 'assistant',
          contents: [{ type: 'text', text: contentText }],
          timestamp: new Date(m.created_at),
          lifecycleStatus: 'completed',
          sources: sources.length ? sources : undefined,
          citationSources: sources.length ? citationSources : undefined,
          followUpSuggestions: m.follow_up_suggestions.length ? m.follow_up_suggestions : undefined,
          feedbackContext: previousUser
            ? {
                question: getMessageText(previousUser),
                answer: m.content,
                title: detail.title ?? undefined,
                sources: m.sources,
                followUps: m.follow_up_suggestions,
                nRetrieved: m.sources.length,
                usage: m.usage,
              }
            : undefined,
        });
      }
    }
    setMessages(restored);
    messagesRef.current = restored;
  }, []);

  return { messages, isStreaming, runState, conversationTitle, sessionId, sendMessage, stopGenerating, regenerateMessage, sendFeedback, clearMessages, loadSession };
}
