import { useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { Loader2, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';

// Use local worker bundled by Vite to avoid CORS issues with unpkg CDN
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

interface Bbox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface PdfGroundingViewerProps {
  url: string;
  bboxes: Bbox[];
  initialPageIdx?: number;
}

export default function PdfGroundingViewer({ url, bboxes, initialPageIdx }: PdfGroundingViewerProps) {
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(
    initialPageIdx !== undefined ? initialPageIdx + 1 : (bboxes[0]?.page !== undefined ? bboxes[0].page + 1 : 1)
  );
  const [numPages, setNumPages] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState<number>(1.5);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-fit to width initially
  const autoFitScale = useRef(false);

  // Load PDF document
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    
    const loadingTask = pdfjsLib.getDocument(url);
    
    loadingTask.promise.then((loadedPdf) => {
      if (!active) return;
      setPdf(loadedPdf);
      setNumPages(loadedPdf.numPages);
      setLoading(false);
    }).catch((err) => {
      if (!active) return;
      console.error('Error loading PDF:', err);
      setError('Impossible de charger le PDF.');
      setLoading(false);
    });

    return () => {
      active = false;
      loadingTask.destroy();
    };
  }, [url]);

  // Render Page and BBoxes
  useEffect(() => {
    if (!pdf || !canvasRef.current || !overlayRef.current) return;

    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    const context = canvas.getContext('2d');
    const overlayContext = overlay.getContext('2d');
    if (!context || !overlayContext) return;

    let renderTask: pdfjsLib.RenderTask | null = null;
    let cancelled = false;

    pdf.getPage(currentPage).then((page) => {
      if (cancelled) return;

      let currentScale = scale;

      // Auto-fit to container on first render
      if (containerRef.current && !autoFitScale.current) {
        const viewport = page.getViewport({ scale: 1 });
        const containerWidth = containerRef.current.clientWidth - 32;
        if (viewport.width > 0) {
          currentScale = Math.max(0.5, Math.min(containerWidth / viewport.width, 3));
          setScale(currentScale);
        }
        autoFitScale.current = true;
      }

      const viewport = page.getViewport({ scale: currentScale });

      canvas.width = viewport.width;
      canvas.height = viewport.height;
      overlay.width = viewport.width;
      overlay.height = viewport.height;

      renderTask = page.render({ canvasContext: context, viewport });

      return renderTask.promise.then(() => {
        // Draw bboxes for the current page (bbox.page is 0-indexed, currentPage is 1-indexed)
        overlayContext.clearRect(0, 0, overlay.width, overlay.height);

        const pageBboxes = bboxes.filter(b => b.page === currentPage - 1);
        if (pageBboxes.length === 0) return;

        // Auto-detect coordinate system (mirrors draw_chunks.py heuristic):
        //   - Docling  → normalized [0, 1000], top-left origin
        //   - MinerU   → PDF pts,              top-left origin
        // Both use top-left origin, so NO PDF-space y-flip needed.
        // viewport.convertToViewportPoint() expects PDF bottom-left coords → don't use it.
        const isNormalized = bboxes.every(b =>
          b.x0 <= 1001 && b.y0 <= 1001 && b.x1 <= 1001 && b.y1 <= 1001
        );

        pageBboxes.forEach(bbox => {
          let cx0: number, cy0: number, cx1: number, cy1: number;

          if (isNormalized) {
            // Docling [0, 1000] → canvas px: scale by viewport dimensions
            cx0 = (bbox.x0 / 1000) * viewport.width;
            cy0 = (bbox.y0 / 1000) * viewport.height;
            cx1 = (bbox.x1 / 1000) * viewport.width;
            cy1 = (bbox.y1 / 1000) * viewport.height;
          } else {
            // MinerU pts, top-left → canvas px: multiply by render scale
            cx0 = bbox.x0 * viewport.scale;
            cy0 = bbox.y0 * viewport.scale;
            cx1 = bbox.x1 * viewport.scale;
            cy1 = bbox.y1 * viewport.scale;
          }

          const rectX = Math.min(cx0, cx1);
          const rectY = Math.min(cy0, cy1);
          const rectW = Math.abs(cx1 - cx0);
          const rectH = Math.abs(cy1 - cy0);

          if (rectW < 1 || rectH < 1) return;

          overlayContext.fillStyle = 'rgba(59, 130, 246, 0.20)';
          overlayContext.fillRect(rectX, rectY, rectW, rectH);
          overlayContext.strokeStyle = 'rgba(59, 130, 246, 0.75)';
          overlayContext.lineWidth = 2;
          overlayContext.strokeRect(rectX, rectY, rectW, rectH);
        });
      });
    }).catch((err: { name?: string }) => {
      if (err?.name !== 'RenderingCancelledException') {
        console.error('PDF render error:', err);
      }
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdf, currentPage, scale, bboxes]);

  return (
    <div className="flex flex-col h-full bg-muted/20">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between p-2 border-b border-border bg-background gap-2 shadow-sm relative z-10">
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="icon" 
            className="h-8 w-8"
            disabled={!pdf || currentPage <= 1}
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-xs text-muted-foreground font-medium min-w-[80px] text-center">
            {numPages > 0 ? `Page ${currentPage} / ${numPages}` : 'Chargement...'}
          </span>
          <Button 
            variant="outline" 
            size="icon" 
            className="h-8 w-8"
            disabled={!pdf || currentPage >= numPages}
            onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="flex items-center gap-2">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8"
            onClick={() => setScale(s => Math.max(0.5, s - 0.25))}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-xs tabular-nums w-12 text-center text-muted-foreground font-medium">
            {Math.round(scale * 100)}%
          </span>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8"
            onClick={() => setScale(s => Math.min(3, s + 0.25))}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>
      
      {/* Viewer Area */}
      <div ref={containerRef} className="flex-1 overflow-auto p-4 flex justify-center bg-muted/10 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-destructive font-medium">{error}</p>
          </div>
        )}
        
        <div 
          className="relative shadow-xl ring-1 ring-border/50 bg-white" 
          style={{ width: canvasRef.current?.width, height: canvasRef.current?.height }}
        >
          <canvas ref={canvasRef} className="block" />
          <canvas ref={overlayRef} className="absolute inset-0 pointer-events-none" />
        </div>
      </div>
    </div>
  );
}
