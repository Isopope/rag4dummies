import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2 } from 'lucide-react';
import type { AgentStep } from '@/types/chat';
import { cn } from '@/lib/utils';

interface AgentStepsTimelineProps {
  steps: AgentStep[];
  isStreaming?: boolean;
  className?: string;
}

const StepIcon = ({ step }: { step: AgentStep }) => {
  if (step.status === 'running') {
    return <Loader2 className="w-3.5 h-3.5 text-primary animate-spin-slow shrink-0" />;
  }
  return <CheckCircle2 className="w-3.5 h-3.5 text-[hsl(var(--success))] shrink-0" />;
};

const AgentStepsTimeline = ({ steps, isStreaming, className }: AgentStepsTimelineProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!steps || steps.length === 0) {
    if (!isStreaming) return null;
    return (
      <div className={cn('flex items-center gap-2 px-3 py-2', className)}>
        <Loader2 className="w-3.5 h-3.5 text-primary animate-spin-slow" />
        <span className="text-xs text-muted-foreground animate-shimmer">
          Réflexion en cours…
        </span>
      </div>
    );
  }

  const completedCount = steps.filter((s) => s.status === 'done').length;
  const currentStep = steps.find((s) => s.status === 'running');
  const isDone = !isStreaming && !currentStep;

  const headerText = isDone
    ? `${completedCount} étape${completedCount > 1 ? 's' : ''} effectuée${completedCount > 1 ? 's' : ''}`
    : currentStep
      ? currentStep.message
      : `${completedCount} étape${completedCount > 1 ? 's' : ''}…`;

  return (
    <div className={cn('rounded-xl border border-[hsl(var(--timeline-border))] bg-[hsl(var(--timeline-bg))] overflow-hidden transition-all duration-300', className)}>
      {/* Header — clickable toggle */}
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[hsl(var(--timeline-border)/0.3)] transition-colors"
      >
        {isDone ? (
          <CheckCircle2 className="w-4 h-4 text-[hsl(var(--success))] shrink-0" />
        ) : (
          <Loader2 className="w-4 h-4 text-primary animate-spin-slow shrink-0" />
        )}

        <span className={cn(
          'flex-1 text-left text-xs font-medium truncate',
          isDone ? 'text-muted-foreground' : 'text-foreground'
        )}>
          {headerText}
        </span>

        {isDone && (
          <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums">
            {formatDuration(steps)}
          </span>
        )}

        {isExpanded
          ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        }
      </button>

      {/* Expanded step list */}
      {isExpanded && (
        <div className="border-t border-[hsl(var(--timeline-border))] animate-slide-in-top">
          <div className="px-3 py-2 space-y-1.5">
            {steps.map((step, i) => (
              <div
                key={`${step.node}-${i}`}
                className="flex items-start gap-2 relative"
              >
                {/* Vertical connector line */}
                {i < steps.length - 1 && (
                  <div className="absolute left-[6.5px] top-[18px] w-px h-[calc(100%+2px)] bg-[hsl(var(--timeline-border))]" />
                )}

                <div className="mt-0.5 relative z-10">
                  <StepIcon step={step} />
                </div>

                <div className="flex-1 min-w-0 pb-1">
                  <p className={cn(
                    'text-xs leading-relaxed break-anywhere',
                    step.status === 'running' ? 'text-foreground font-medium' : 'text-muted-foreground'
                  )}>
                    {step.message}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

/** Format total pipeline duration from first to last step */
function formatDuration(steps: AgentStep[]): string {
  if (steps.length < 2) return '';
  const first = steps[0].timestamp.getTime();
  const last = steps[steps.length - 1].timestamp.getTime();
  const seconds = Math.round((last - first) / 1000);
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

export default AgentStepsTimeline;
