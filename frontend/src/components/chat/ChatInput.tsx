import { useState, useRef, useEffect, useCallback, FormEvent, KeyboardEvent } from 'react';
import { ArrowUp, Square, PlusCircle } from 'lucide-react';
import { ChatInputImagePreview } from './ChatInputImagePreview';
import { ChatInputModelSelect, MOCK_MODELS } from './ChatInputModelSelect';
import { useImageUpload, type UploadedImage } from '@/hooks/use-image-upload';
import { cn } from '@/lib/utils';

const MIN_INPUT_HEIGHT = 44;
const MAX_INPUT_HEIGHT = 200;

export interface ChatInputSubmitPayload {
  text: string;
  images: UploadedImage[];
  modelId: string;
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
  const [modelId, setModelId] = useState(MOCK_MODELS[0].id);
  const [isDragging, setIsDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);
  const imageUpload = useImageUpload();

  const handleSend = useCallback(() => {
    const trimmed = message.trim();
    if ((!trimmed && !imageUpload.hasImages) || disabled) return;
    onSend({ text: trimmed, images: imageUpload.images, modelId });
    setMessage('');
    imageUpload.clearImages();
    if (wrapperRef.current) wrapperRef.current.style.height = `${MIN_INPUT_HEIGHT}px`;
  }, [message, imageUpload, disabled, onSend, modelId]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as any).isComposing) {
      e.preventDefault();
      if (isStreaming) return;
      handleSend();
    }
  };

  // Auto-resize textarea (Onyx pattern)
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

  // Drag & drop
  useEffect(() => {
    const el = dropZoneRef.current;
    if (!el) return;
    let counter = 0;

    const onEnter = (e: DragEvent) => { e.preventDefault(); counter++; if (e.dataTransfer?.types.includes('Files')) setIsDragging(true); };
    const onLeave = (e: DragEvent) => { e.preventDefault(); counter--; if (counter === 0) setIsDragging(false); };
    const onOver = (e: DragEvent) => e.preventDefault();
    const onDrop = (e: DragEvent) => { e.preventDefault(); counter = 0; setIsDragging(false); if (e.dataTransfer?.files) imageUpload.addFiles(e.dataTransfer.files); };

    el.addEventListener('dragenter', onEnter);
    el.addEventListener('dragleave', onLeave);
    el.addEventListener('dragover', onOver);
    el.addEventListener('drop', onDrop);
    return () => { el.removeEventListener('dragenter', onEnter); el.removeEventListener('dragleave', onLeave); el.removeEventListener('dragover', onOver); el.removeEventListener('drop', onDrop); };
  }, [imageUpload.addFiles]); // eslint-disable-line react-hooks/exhaustive-deps

  // Paste images
  useEffect(() => {
    const handler = (e: ClipboardEvent) => {
      if (dropZoneRef.current?.contains(e.target as Node)) imageUpload.handlePaste(e);
    };
    document.addEventListener('paste', handler);
    return () => document.removeEventListener('paste', handler);
  }, [imageUpload.handlePaste]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasContent = message.trim() || imageUpload.hasImages;
  const showFiles = imageUpload.images.length > 0;

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="max-w-[var(--app-page-main-content-width)] mx-auto">
        <form onSubmit={handleSubmit}>
          <div
            ref={dropZoneRef}
            className={cn(
              'relative flex flex-col bg-[hsl(var(--chat-input))] rounded-2xl shadow-md border border-border/50 transition-all',
              'focus-within:shadow-lg focus-within:border-primary/20',
              isDragging && 'ring-2 ring-primary border-primary/50',
            )}
          >
            {/* Drop overlay */}
            {isDragging && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-primary/5 border-2 border-dashed border-primary/40 pointer-events-none">
                <p className="text-sm font-medium text-primary">Déposer les images ici</p>
              </div>
            )}

            {/* Attached images */}
            {showFiles && (
              <div className="px-3 pt-3 transition-all duration-150">
                <ChatInputImagePreview images={imageUpload.images} onRemove={imageUpload.removeImage} />
              </div>
            )}

            {/* Hidden file input */}
            <input
              ref={imageUpload.inputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => { if (e.target.files) imageUpload.addFiles(e.target.files); e.target.value = ''; }}
            />

            {/* Textarea row */}
            <div ref={wrapperRef} className="px-3 py-2 flex-1 flex min-h-[44px]">
              <textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isStreaming ? 'En cours de génération...' : 'Comment puis-je vous aider ?'}
                rows={1}
                disabled={disabled}
                autoFocus
                className={cn(
                  'w-full h-full outline-none bg-transparent resize-none text-sm text-foreground',
                  'placeholder:text-muted-foreground whitespace-pre-wrap break-words',
                  'overflow-y-auto p-[2px]',
                )}
                style={{ scrollbarWidth: 'thin' }}
                aria-multiline
              />
            </div>

            {/* Bottom controls bar */}
            <div className="flex items-center justify-between px-2 pb-2">
              {/* Left: attach + model */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => imageUpload.openPicker()}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
                  title="Attacher des fichiers"
                >
                  <PlusCircle className="w-4.5 h-4.5" />
                </button>
                <ChatInputModelSelect value={modelId} onChange={setModelId} />
              </div>

              {/* Right: send / stop */}
              <button
                type={isStreaming ? 'button' : 'submit'}
                disabled={!isStreaming && (!hasContent || disabled)}
                onClick={isStreaming ? onStopGenerating : undefined}
                className={cn(
                  'p-2 rounded-xl transition-all',
                  isStreaming
                    ? 'bg-destructive/90 text-destructive-foreground hover:bg-destructive'
                    : 'bg-primary text-primary-foreground hover:opacity-90',
                  !isStreaming && (!hasContent || disabled) && 'opacity-30 cursor-not-allowed',
                )}
                aria-label={isStreaming ? 'Arrêter la génération' : 'Envoyer le message'}
              >
                {isStreaming ? (
                  <Square className="w-4 h-4" />
                ) : (
                  <ArrowUp className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </form>

        <p className="text-[10px] text-muted-foreground text-center mt-2 opacity-60">
          Les réponses sont générées à partir de vos documents indexés.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
