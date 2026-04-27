import { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import { Bot, ArrowDown } from 'lucide-react';
import { ChatMessage, MessageFeedback } from '@/types/chat';
import MessageRenderer from './MessageRenderer';
import FollowUpSuggestions from './FollowUpSuggestions';
import { AssistantMessageActions } from './AssistantMessageActions';
import AgentStepsTimeline from './AgentStepsTimeline';
import { cn } from '@/lib/utils';

interface ChatAreaProps {
  messages: ChatMessage[];
  isTyping?: boolean;
  onSelectSuggestion?: (suggestion: string) => void;
  onFeedback?: (messageId: string, feedback: MessageFeedback) => void;
  onRegenerate?: (messageId: string) => void;
  onShowSources?: (message: ChatMessage) => void;
}

/* ── Random greetings (Onyx-inspired) ──────────────────────────────── */
const GREETINGS = [
  'Bonjour ! Comment puis-je vous aider ?',
  'Posez-moi une question sur vos documents.',
  'Je suis prêt à explorer vos données.',
  'Que souhaitez-vous découvrir aujourd\'hui ?',
];

const getGreeting = () => GREETINGS[Math.floor(Math.random() * GREETINGS.length)];

/* ── Welcome screen (0 messages) ───────────────────────────────────── */
const WelcomeScreen = ({ greeting, onSelect }: { greeting: string; onSelect?: (s: string) => void }) => (
  <div className="flex-1 flex items-center justify-center animate-fade-in">
    <div className="flex flex-col items-center gap-6 max-w-lg text-center px-4">
      {/* Go4AI logo */}
      <img src="/go4aiLogo.png" alt="Go4AI" className="h-16 w-auto" />

      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-foreground">{greeting}</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Je réponds à vos questions à partir de vos documents indexés —
          tableaux, graphiques et données structurées inclus.
        </p>
      </div>

      {/* Starter suggestions */}
      {onSelect && (
        <div className="flex flex-wrap justify-center gap-2 mt-1">
          {['Résume le document principal', 'Quels sont les points clés ?', 'Compare les sources disponibles'].map(
            (s) => (
              <button
                key={s}
                onClick={() => onSelect(s)}
                className="px-4 py-2 text-xs rounded-full border border-border bg-card hover:bg-secondary/60 text-foreground transition-colors font-medium shadow-sm"
              >
                {s}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  </div>
);

/* ── User message (right-aligned bubble) ───────────────────────────── */
const UserMessage = ({ msg }: { msg: ChatMessage }) => (
  <div className="flex justify-end animate-fade-in group">
    {/* Edit/copy buttons appear on hover */}
    <div className="flex items-start gap-2">
      <div className="max-w-[30rem] md:max-w-[37.5rem]">
        {/* Attached images */}
        {msg.attachedImages && msg.attachedImages.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 justify-end">
            {msg.attachedImages.map((img) => (
              <img
                key={img.id}
                src={img.url}
                alt={img.name}
                className="h-24 w-24 object-cover rounded-xl border border-border"
              />
            ))}
          </div>
        )}

        {/* Text bubble */}
        <div className="whitespace-pre-wrap break-anywhere rounded-t-2xl rounded-bl-2xl bg-[hsl(var(--user-bubble))] text-[hsl(var(--user-bubble-foreground))] py-2.5 px-3.5 shadow-sm">
          {msg.contents.map((content, i) => (
            <MessageRenderer key={i} content={content} />
          ))}
        </div>
      </div>
    </div>
  </div>
);

/* ── Assistant message (left-aligned, full width, no bubble) ───────── */
const AssistantMessage = ({
  msg,
  onFeedback,
  onRegenerate,
  onShowSources,
  onSelectSuggestion,
}: {
  msg: ChatMessage;
  onFeedback?: (id: string, fb: MessageFeedback) => void;
  onRegenerate?: (id: string) => void;
  onShowSources?: (msg: ChatMessage) => void;
  onSelectSuggestion?: (s: string) => void;
}) => (
  <div className="flex items-start gap-3 animate-fade-in">
    {/* Agent avatar */}
    <div className="shrink-0 w-7 h-7 rounded-lg bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center mt-0.5">
      <Bot className="w-4 h-4 text-primary" />
    </div>

    <div className="flex-1 min-w-0 flex flex-col gap-2">
      {/* Timeline of agent steps */}
      {msg.steps && msg.steps.length > 0 && (
        <AgentStepsTimeline
          steps={msg.steps}
          isStreaming={msg.isStreaming}
        />
      )}

      {/* Streaming shimmer when no text yet */}
      {msg.isStreaming && (!msg.contents[0]?.text) && !msg.steps?.length && (
        <div className="flex items-center gap-2 py-1">
          <span className="text-sm animate-shimmer">Réflexion en cours…</span>
        </div>
      )}

      {/* Message content */}
      {msg.contents.some((c) => c.type === 'text' ? (c.text ?? '').length > 0 : true) && (
        <div className="text-[hsl(var(--agent-message-foreground))] select-text">
          {msg.contents.map((content, i) => (
            <MessageRenderer key={i} content={content} />
          ))}
        </div>
      )}

      {/* Toolbar (only when not streaming) */}
      {!msg.isStreaming && (
        <>
          <AssistantMessageActions
            message={msg}
            onFeedback={onFeedback}
            onRegenerate={onRegenerate}
            onShowSources={onShowSources}
            className="-ml-1 mt-0.5"
          />
          {msg.followUpSuggestions && onSelectSuggestion && (
            <FollowUpSuggestions
              suggestions={msg.followUpSuggestions}
              onSelect={onSelectSuggestion}
            />
          )}
        </>
      )}
    </div>
  </div>
);

/* ── Main ChatArea ─────────────────────────────────────────────────── */
const ChatArea = ({
  messages,
  isTyping,
  onSelectSuggestion,
  onFeedback,
  onRegenerate,
  onShowSources,
}: ChatAreaProps) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const greeting = useMemo(getGreeting, []);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(distanceFromBottom > 120);
  }, []);

  useEffect(() => {
    // Auto-scroll only when already near the bottom
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 120) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isTyping]);

  if (messages.length === 0) {
    return <WelcomeScreen greeting={greeting} onSelect={onSelectSuggestion} />;
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto scrollbar-thin"
      >
        <div className="mx-auto w-full max-w-[var(--app-page-main-content-width)] py-6 px-4 space-y-6">
          {messages.map((msg) =>
            msg.role === 'user' ? (
              <UserMessage key={msg.id} msg={msg} />
            ) : (
              <AssistantMessage
                key={msg.id}
                msg={msg}
                onFeedback={onFeedback}
                onRegenerate={onRegenerate}
                onShowSources={onShowSources}
                onSelectSuggestion={onSelectSuggestion}
              />
            ),
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Scroll-to-bottom floating button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 z-10 flex items-center justify-center w-8 h-8 rounded-full bg-background border border-border shadow-md text-muted-foreground hover:text-foreground hover:shadow-lg transition-all animate-fade-in"
          title="Retour en bas"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};

export default ChatArea;
