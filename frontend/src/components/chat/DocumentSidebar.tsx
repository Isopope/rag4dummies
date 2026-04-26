import { ExternalLink, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MessageSource } from '@/types/chat';

interface DocumentSidebarProps {
  sources: MessageSource[];
  messageId?: string | null;
  onClose: () => void;
}

export function DocumentSidebar({ sources, messageId, onClose }: DocumentSidebarProps) {
  return (
    <aside className="h-full w-full border-l border-border bg-card shadow-lg">
      <div className="flex h-12 items-center justify-between border-b border-border px-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground">Documents</h2>
          {messageId && <p className="text-[10px] text-muted-foreground">Réponse #{messageId}</p>}
        </div>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="h-[calc(100%-3rem)] overflow-y-auto p-4 scrollbar-thin">
        <div className="space-y-3">
          {sources.map((source, index) => (
            <article key={source.id} className="rounded-lg border border-border bg-background p-3">
              <div className="mb-2 flex items-start gap-2">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10">
                  <FileText className="h-3.5 w-3.5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] uppercase text-muted-foreground">Source {index + 1}</p>
                  <h3 className="truncate text-sm font-medium text-foreground">{source.title}</h3>
                </div>
              </div>
              {source.excerpt && <p className="text-xs leading-relaxed text-muted-foreground">{source.excerpt}</p>}
              {source.url && (
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  <Button type="button" variant="ghost" size="sm" className="mt-3 h-7 px-2 text-xs">
                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                    Ouvrir
                  </Button>
                </a>
              )}
            </article>
          ))}
        </div>
      </div>
    </aside>
  );
}

export default DocumentSidebar;