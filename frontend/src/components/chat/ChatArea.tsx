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
  onRegenerate?: (messageId: string, modelId?: string) => void;
  onShowSources?: (message: ChatMessage) => void;
}

/* ── Greetings ──────────────────────────────────────────────────────── */
const GREETINGS = [
  'Bonjour, que puis-je éclairer pour vous ?',
  'Vos documents, à portée de question.',
  'Interrogez l\'intelligence de vos données.',
  'Que souhaitez-vous explorer aujourd\'hui ?',
];

const getGreeting = () => GREETINGS[Math.floor(Math.random() * GREETINGS.length)];

const STAGGER = ['stagger-1', 'stagger-2', 'stagger-3'] as const;

/* ── Welcome screen (0 messages) ───────────────────────────────────── */
const WelcomeScreen = ({ greeting, onSelect }: { greeting: string; onSelect?: (s: string) => void }) => (
  <div className="flex-1 flex items-center justify-center relative overflow-hidden animate-fade-in">
    {/* Atmospheric dot grid */}
    <div className="absolute inset-0 welcome-dot-grid" />
    <div className="absolute inset-0 bg-gradient-to-b from-background/20 via-background/70 to-background pointer-events-none" />

    <div className="relative z-10 flex flex-col items-center gap-8 max-w-xl text-center px-8">
      {/* Brand mark */}
      <div className="flex flex-col items-center gap-3">
        <img src="/go4aiLogo.png" alt="Go4AI" className="h-14 w-auto" />
        <div className="flex items-center gap-3">
          <div className="w-6 h-px bg-accent/60" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Intelligence documentaire
          </span>
          <div className="w-6 h-px bg-accent/60" />
        </div>
      </div>

      {/* Headline */}
      <div className="space-y-3">
        <h2 className="font-display text-4xl font-light tracking-tight text-foreground leading-[1.1]">
          {greeting}
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed max-w-sm mx-auto">
          Indexez, interrogez et analysez vos données internes avec précision.
        </p>
      </div>

      {/* Starter suggestions — staggered entrance */}
      {onSelect && (
        <div className="flex flex-wrap justify-center gap-2.5">
          {(['Résume le document principal', 'Quels sont les points clés ?', 'Compare les sources disponibles'] as const).map(
            (s, i) => (
              <button
                key={s}
                onClick={() => onSelect(s)}
                className={`px-5 py-2 text-xs rounded-full border border-border/70 bg-card/80 backdrop-blur-sm hover:bg-accent hover:text-accent-foreground hover:border-accent text-foreground transition-all duration-200 font-medium shadow-sm animate-fade-in ${STAGGER[i]}`}
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
  onRegenerate?: (id: string, modelId?: string) => void;
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
  const latestAssistantMessageId = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'assistant') return messages[index].id;
    }
    return null;
  }, [messages]);

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
                onRegenerate={msg.id === latestAssistantMessageId ? onRegenerate : undefined}
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
