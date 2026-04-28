import { ExternalLink, FileText, X, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MessageSource } from '@/types/chat';

interface DocumentSidebarProps {
  sources: MessageSource[];
  messageId?: string | null;
  onClose: () => void;
  onOpenViewer?: (source: MessageSource) => void;
}

export function DocumentSidebar({ sources, messageId, onClose, onOpenViewer }: DocumentSidebarProps) {
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
          {sources.map((source, index) => {
            const hasBboxes = source.bboxes && source.bboxes.length > 0;
            const hasPdfUrl = !!source.url;
            const canView = hasBboxes && hasPdfUrl;

            return (
              <article key={source.id} className="rounded-lg border border-border bg-background p-3">
                <div className="mb-2 flex items-start gap-2">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10">
                    <FileText className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[10px] uppercase text-muted-foreground">Source {index + 1}</p>
                      {source.kind && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-sm bg-muted text-muted-foreground font-medium uppercase tracking-wider">
                          {source.kind}
                        </span>
                      )}
                    </div>
                    <h3 className="truncate text-sm font-medium text-foreground mt-0.5" title={source.title}>{source.title}</h3>
                  </div>
                </div>
                {source.excerpt && <p className="text-xs leading-relaxed text-muted-foreground">{source.excerpt}</p>}
                
                <div className="mt-3 flex items-center gap-2">
                  {canView && onOpenViewer && (
                    <Button 
                      type="button" 
                      variant="secondary" 
                      size="sm" 
                      className="h-7 px-2.5 text-xs text-primary bg-primary/10 hover:bg-primary/20 hover:text-primary"
                      onClick={() => onOpenViewer(source)}
                    >
                      <Eye className="mr-1.5 h-3.5 w-3.5" />
                      Voir dans le PDF
                    </Button>
                  )}
                  
                  {source.url && (
                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs">
                        <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                        Ouvrir
                      </Button>
                    </a>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

export default DocumentSidebar;