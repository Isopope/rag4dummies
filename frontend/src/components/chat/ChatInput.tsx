import { useState, useRef, useEffect, useCallback, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { ChatInputModelSelect } from './ChatInputModelSelect';
import { ChatInputRuntimeSelect } from './ChatInputRuntimeSelect';
import { cn } from '@/lib/utils';

const MIN_INPUT_HEIGHT = 44;
const MAX_INPUT_HEIGHT = 200;

export interface ChatInputSubmitPayload {
  text: string;
  modelId: string;
  engineId: string;
}

interface ChatInputProps {
  onSend: (payload: ChatInputSubmitPayload) => void;
  disabled?: boolean;
  showSuggestions?: boolean;
  /** When true, the send button becomes a stop button */
  isStreaming?: boolean;
  onStopGenerating?: () => void;
}

const ChatInput = ({
  onSend,
  disabled,
  isStreaming,
  onStopGenerating,
}: ChatInputProps) => {
  const [message, setMessage] = useState('');
  const [modelId, setModelId] = useState('');
  const [engineId, setEngineId] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = message.trim();
    if (!trimmed || disabled) return;
    onSend({ text: trimmed, modelId, engineId });
    setMessage('');
    if (wrapperRef.current) wrapperRef.current.style.height = `${MIN_INPUT_HEIGHT}px`;
  }, [message, disabled, onSend, modelId, engineId]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    const nativeEvent = e.nativeEvent as Event & { isComposing?: boolean };
    if (e.key === 'Enter' && !e.shiftKey && !nativeEvent.isComposing) {
      e.preventDefault();
      if (isStreaming) return;
      handleSend();
    }
  };

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const textarea = textareaRef.current;
    if (!wrapper || !textarea) return;

    wrapper.style.height = `${MIN_INPUT_HEIGHT}px`;
    const style = getComputedStyle(wrapper);
    const paddingTop = parseFloat(style.paddingTop);
    const paddingBottom = parseFloat(style.paddingBottom);
    const contentHeight = textarea.scrollHeight + paddingTop + paddingBottom;
    wrapper.style.height = `${Math.min(Math.max(contentHeight, MIN_INPUT_HEIGHT), MAX_INPUT_HEIGHT)}px`;
  }, [message]);

  const hasContent = message.trim().length > 0;

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="max-w-[var(--app-page-main-content-width)] mx-auto">
        <form onSubmit={handleSubmit}>
          <div
            className={cn(
              'relative flex flex-col rounded-2xl border border-border/50 bg-[hsl(var(--chat-input))] shadow-md transition-all',
              'focus-within:border-primary/20 focus-within:shadow-lg',
            )}
          >
            <div ref={wrapperRef} className="flex min-h-[44px] flex-1 px-3 py-2">
              <textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isStreaming ? 'En cours de generation...' : 'Comment puis-je vous aider ?'}
                rows={1}
                disabled={disabled}
                autoFocus
                className={cn(
                  'h-full w-full resize-none bg-transparent p-[2px] text-sm text-foreground outline-none',
                  'whitespace-pre-wrap break-words placeholder:text-muted-foreground',
                  'overflow-y-auto',
                )}
                style={{ scrollbarWidth: 'thin' }}
                aria-multiline
              />
            </div>

            <div className="flex items-center justify-between px-2 pb-2">
              <div className="flex items-center gap-1">
                <ChatInputRuntimeSelect value={engineId} onChange={setEngineId} />
                <ChatInputModelSelect value={modelId} onChange={setModelId} />
              </div>

              <button
                type={isStreaming ? 'button' : 'submit'}
                disabled={!isStreaming && (!hasContent || disabled)}
                onClick={isStreaming ? onStopGenerating : undefined}
                className={cn(
                  'rounded-xl p-2 transition-all',
                  isStreaming
                    ? 'bg-destructive/90 text-destructive-foreground hover:bg-destructive'
                    : 'bg-primary text-primary-foreground hover:opacity-90',
                  !isStreaming && (!hasContent || disabled) && 'cursor-not-allowed opacity-30',
                )}
                aria-label={isStreaming ? 'Arreter la generation' : 'Envoyer le message'}
              >
                {isStreaming ? (
                  <Square className="h-4 w-4" />
                ) : (
                  <ArrowUp className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </form>

        <p className="mt-2 text-center text-[10px] text-muted-foreground opacity-60">
          Les reponses sont generees a partir de vos documents indexes.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
