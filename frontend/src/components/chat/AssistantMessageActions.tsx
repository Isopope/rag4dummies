import { useState } from 'react';
import type { ComponentProps, FormEvent, KeyboardEvent } from 'react';
import { ThumbsUp, ThumbsDown, Copy, Check, FileText, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { ChatInputModelSelect } from './ChatInputModelSelect';
import { cn } from '@/lib/utils';
import type { ChatMessage, MessageFeedback } from '@/types/chat';

interface AssistantMessageActionsProps {
  message: ChatMessage;
  className?: string;
  onFeedback?: (messageId: string, feedback: MessageFeedback) => void;
  onRegenerate?: (messageId: string, modelId?: string) => void;
  onShowSources?: (message: ChatMessage) => void;
}

/* ── Inline icon button with tooltip ───────────────────────────────── */
const ToolbarButton = ({
  label,
  children,
  className,
  ...props
}: ComponentProps<typeof Button> & { label: string }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={label}
        className={cn(
          'h-7 w-7 text-muted-foreground hover:text-foreground transition-colors',
          className,
        )}
        {...props}
      >
        {children}
      </Button>
    </TooltipTrigger>
    <TooltipContent side="bottom" className="text-xs">{label}</TooltipContent>
  </Tooltip>
);

const getMessageText = (message: ChatMessage): string =>
  message.contents
    .map((c) => {
      if (c.type === 'text') return c.text ?? '';
      if (c.type === 'code') return c.code ?? '';
      if (c.type === 'json') return JSON.stringify(c.jsonData, null, 2);
      return '';
    })
    .filter(Boolean)
    .join('\n\n');

/* ── Regenerate button with inline model picker ─────────────────────── */
const RegenerateButton = ({
  messageId,
  onRegenerate,
}: {
  messageId: string;
  onRegenerate: (messageId: string, modelId?: string) => void;
}) => {
  const [open, setOpen] = useState(false);
  const [modelId, setModelId] = useState('');

  const handleModelChange = (nextModelId: string) => {
    setModelId(nextModelId);
    setOpen(false);
    onRegenerate(messageId, nextModelId || undefined);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) setModelId('');
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Régénérer"
              className="h-7 w-7 text-muted-foreground hover:text-foreground transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">Régénérer</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-64 p-3 space-y-3">
        <p className="text-xs font-medium text-foreground">Régénérer avec</p>
        <ChatInputModelSelect
          value={modelId}
          onChange={handleModelChange}
          autoSelectDefault={false}
          placeholder="Choisir un modele"
        />
      </PopoverContent>
    </Popover>
  );
};

/* ── Main toolbar ──────────────────────────────────────────────────── */
export const AssistantMessageActions = ({
  message,
  className,
  onFeedback,
  onRegenerate,
  onShowSources,
}: AssistantMessageActionsProps) => {
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const { isCopied, copy } = useCopyToClipboard();

  const currentVote = message.feedback?.vote;

  const handleLike = () => {
    if (currentVote === 'up') return;
    onFeedback?.(message.id, { vote: 'up' });
  };

  const handleDislikeSubmit = (explanation?: string) => {
    setIsPending(true);
    onFeedback?.(message.id, { vote: 'down', explanation });
    setShowFeedbackDialog(false);
    setIsPending(false);
  };

  return (
    <>
      <TooltipProvider delayDuration={200}>
        <div className={cn('flex items-center gap-0.5', className)}>
          {/* Like */}
          <ToolbarButton
            onClick={handleLike}
            label={currentVote === 'up' ? 'Retirer le like' : 'Bonne réponse'}
            className={cn(currentVote === 'up' && 'text-primary')}
          >
            <ThumbsUp className="w-3.5 h-3.5" />
          </ToolbarButton>

          {/* Dislike */}
          <ToolbarButton
            onClick={() => setShowFeedbackDialog(true)}
            label={currentVote === 'down' ? 'Modifier le retour' : 'Mauvaise réponse'}
            className={cn(currentVote === 'down' && 'text-destructive')}
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </ToolbarButton>

          {/* Copy */}
          <ToolbarButton
            onClick={() => copy(getMessageText(message))}
            label={isCopied ? 'Copié !' : 'Copier'}
          >
            {isCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          </ToolbarButton>

          {/* Regenerate with model picker */}
          {onRegenerate && (
            <RegenerateButton messageId={message.id} onRegenerate={onRegenerate} />
          )}

          {/* Sources count badge */}
          {message.sources && message.sources.length > 0 && onShowSources && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => onShowSources(message)}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span className="tabular-nums">{message.sources.length}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                Voir les sources
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </TooltipProvider>

      <NegativeFeedbackDialog
        open={showFeedbackDialog}
        onOpenChange={setShowFeedbackDialog}
        onSubmit={handleDislikeSubmit}
        isPending={isPending}
      />
    </>
  );
};

/* ── Negative feedback modal ───────────────────────────────────────── */
interface NegativeFeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (explanation?: string) => void;
  isPending: boolean;
}

const NegativeFeedbackDialog = ({
  open,
  onOpenChange,
  onSubmit,
  isPending,
}: NegativeFeedbackDialogProps) => {
  const [explanation, setExplanation] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(explanation.trim() || undefined);
    setExplanation('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Qu'est-ce qui n'allait pas ?</DialogTitle>
          <DialogDescription>
            Aidez-nous à nous améliorer en expliquant ce qui n'allait pas avec cette réponse.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Textarea
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Réponse imprécise, hors sujet, manque de sources..."
            rows={4}
            className="resize-none"
          />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Annuler
            </Button>
            <Button type="submit" disabled={isPending}>
              Envoyer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AssistantMessageActions;
