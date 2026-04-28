import { useState, useCallback, useRef, useEffect } from 'react';
import { streamQueryRAG, submitFeedback } from '@/lib/api';
import type { ChunkModel, FeedbackPayload, SessionDetail } from '@/lib/api';
import type { ChatMessage, MessageFeedback, MessageSource, AgentStep } from '@/types/chat';
import type { ChatInputSubmitPayload } from '@/components/chat/ChatInput';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

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

function buildSummary(messages: ChatMessage[]): string {
  return messages
    .slice(-6)
    .map((m) => {
      const text = m.contents.find((c) => c.type === 'text')?.text ?? '';
      return `${m.role === 'user' ? 'Utilisateur' : 'Assistant'}: ${text.slice(0, 500)}`;
    })
    .join('\n');
}

interface LastResult {
  questionId: string;
  question: string;
  answer: string;
  sources: ChunkModel[];
  followUps: string[];
  title?: string;
  nRetrieved: number;
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
  const { token } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationTitle, setConversationTitle] = useState<string | undefined>();
  const [sessionId, setSessionId] = useState<string | undefined>();
  const lastResult = useRef<LastResult | null>(null);
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

  const sendMessage = useCallback(async (payload: ChatInputSubmitPayload | string) => {
    const text = typeof payload === 'string' ? payload : payload.text;
    const images = typeof payload === 'string' ? [] : payload.images;
    const modelId = typeof payload === 'string' ? undefined : payload.modelId || undefined;
    if (!text.trim()) return;

    // Cancel any in-progress stream
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const conversationSummary = buildSummary(messagesRef.current);

    // Passe le sessionId courant pour que le backend sauvegarde dans la bonne session
    const currentSessionId = sessionIdRef.current;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      contents: [{ type: 'text', text }],
      timestamp: new Date(),
      attachedImages: images.length
        ? images.map((i) => ({ id: i.id, url: i.url, name: i.name }))
        : undefined,
    };

    const assistantId = `a-${Date.now() + 1}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      contents: [{ type: 'text', text: '' }],
      timestamp: new Date(),
      isStreaming: true,
      steps: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    setIsStreaming(true);

    let accText = '';
    let finalSources: ChunkModel[] = [];
    let finalFollowUps: string[] = [];
    let finalTitle: string | undefined;
    let finalQuestionId: string | undefined;
    const steps: AgentStep[] = [];

    try {
      for await (const event of streamQueryRAG(
        { question: text, conversation_summary: conversationSummary, session_id: currentSessionId, model: modelId },
        controller.signal,
        token,
      )) {
        if (event.type === 'node_update' && event.node) {
          // Mark previous running step as done
          const prev = steps.find((s) => s.status === 'running');
          if (prev) prev.status = 'done';

          // Add new step
          steps.push({
            node: event.node,
            message: event.message || nodeLabel(event.node),
            timestamp: new Date(),
            status: 'running',
          });

          // Update message steps (spread to trigger React re-render)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, steps: [...steps] }
                : m,
            ),
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
          finalSources    = event.sources ?? [];
          finalFollowUps  = event.follow_up_suggestions ?? [];
          finalTitle      = event.conversation_title;
          finalQuestionId = event.question_id;
          // Stocke le session_id retourné par le backend (nouveau ou existant)
          if (event.session_id) setSessionId(event.session_id);
        } else if (event.type === 'error') {
          throw new Error(event.error ?? 'Erreur SSE');
        }
      }

      // Mark all remaining steps as done
      steps.forEach((s) => { s.status = 'done'; });

      if (finalTitle) setConversationTitle(finalTitle);

      lastResult.current = {
        questionId: finalQuestionId ?? '',
        question: text,
        answer: accText,
        sources: finalSources,
        followUps: finalFollowUps,
        title: finalTitle,
        nRetrieved: finalSources.length,
      };

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                contents: [{ type: 'text', text: accText }],
                isStreaming: false,
                sources: finalSources.length ? finalSources.map(chunkToSource) : undefined,
                followUpSuggestions: finalFollowUps.length ? finalFollowUps : undefined,
                steps: [...steps],
              }
            : m,
        ),
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : 'Erreur de connexion';
      toast.error(`Erreur : ${msg}`);
      steps.forEach((s) => { s.status = 'done'; });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                contents: [{ type: 'text', text: `❌ ${msg}` }],
                isStreaming: false,
                steps: [...steps],
              }
            : m,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const sendFeedback = useCallback(async (messageId: string, feedback: MessageFeedback) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, feedback } : m)));
    const result = lastResult.current;
    if (!result) return;
    try {
      const payload: FeedbackPayload = {
        question_id: result.questionId || undefined,
        question: result.question,
        answer: result.answer,
        rating: feedback.vote === 'up' ? 5 : 1,
        comment: feedback.explanation,
        conversation_title: result.title,
        sources: result.sources,
        follow_up_suggestions: result.followUps,
        n_retrieved: result.nRetrieved,
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
    lastResult.current = null;
    messagesRef.current = [];
  }, []);

  /** Restaure une session depuis l'historique (appel à GET /sessions/{id}). */
  const loadSession = useCallback((detail: SessionDetail) => {
    abortRef.current?.abort();
    setSessionId(detail.id);
    setConversationTitle(detail.title ?? undefined);
    lastResult.current = null;

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
        const sources: MessageSource[] = m.sources.map((c) => ({
          id: `${c.source}-${c.chunk_index}`,
          title: c.source.split('/').pop() ?? c.source,
          excerpt: c.page_content.slice(0, 200),
          url: c.pdf_url,
          bboxes: c.bboxes,
          pageIdx: c.page_idx,
          kind: c.kind,
        }));
        restored.push({
          id: m.id,
          role: 'assistant',
          contents: [{ type: 'text', text: m.content }],
          timestamp: new Date(m.created_at),
          sources: sources.length ? sources : undefined,
          followUpSuggestions: m.follow_up_suggestions.length ? m.follow_up_suggestions : undefined,
        });
      }
    }
    setMessages(restored);
    messagesRef.current = restored;
  }, []);

  return { messages, isStreaming, conversationTitle, sessionId, sendMessage, sendFeedback, clearMessages, loadSession };
}
