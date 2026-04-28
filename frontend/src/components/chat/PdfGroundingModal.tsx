import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import PdfGroundingViewer from './PdfGroundingViewer';
import type { MessageSource } from '@/types/chat';

interface PdfGroundingModalProps {
  source: MessageSource | null;
  onClose: () => void;
}

export function PdfGroundingModal({ source, onClose }: PdfGroundingModalProps) {
  if (!source) return null;
  
  return (
    <Dialog open={!!source} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl w-[90vw] h-[90vh] flex flex-col p-0 overflow-hidden bg-background">
        <DialogTitle className="sr-only">Visualiseur PDF</DialogTitle>
        <DialogDescription className="sr-only">Affiche le document source avec surlignage</DialogDescription>
        
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-foreground truncate">{source.title}</h3>
            {source.kind && (
              <p className="text-[10px] uppercase text-muted-foreground mt-0.5">{source.kind}</p>
            )}
          </div>
        </div>
        
        <div className="flex-1 overflow-hidden relative">
          {source.url ? (
            <PdfGroundingViewer 
              url={source.url} 
              bboxes={source.bboxes || []} 
              initialPageIdx={source.pageIdx}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              Le lien du document n'est pas disponible.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
