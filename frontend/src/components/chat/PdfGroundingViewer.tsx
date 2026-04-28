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

    let active = true;
    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    const context = canvas.getContext('2d');
    const overlayContext = overlay.getContext('2d');
    if (!context || !overlayContext) return;

    pdf.getPage(currentPage).then((page) => {
      if (!active) return;
      
      let currentScale = scale;
      
      // Auto-fit to container on first render
      if (containerRef.current && !autoFitScale.current) {
        const viewport = page.getViewport({ scale: 1 });
        const containerWidth = containerRef.current.clientWidth - 32; // padding
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
      
      const renderContext = {
        canvasContext: context,
        viewport: viewport,
      };
      
      const renderTask = page.render(renderContext);
      
      renderTask.promise.then(() => {
        if (!active) return;
        
        // Clear overlay
        overlayContext.clearRect(0, 0, overlay.width, overlay.height);
        
        // Draw bboxes for the current page
        // Note: bbox.page is 0-indexed, currentPage is 1-indexed
        const pageBboxes = bboxes.filter(b => b.page === currentPage - 1);
        
        pageBboxes.forEach(bbox => {
          const [x0, y0] = viewport.convertToViewportPoint(bbox.x0, bbox.y0);
          const [x1, y1] = viewport.convertToViewportPoint(bbox.x1, bbox.y1);
          
          const rectX = Math.min(x0, x1);
          const rectY = Math.min(y0, y1);
          const rectW = Math.abs(x1 - x0);
          const rectH = Math.abs(y1 - y0);
          
          // CSS vars from grounding implementation plan
          overlayContext.fillStyle = 'rgba(59, 130, 246, 0.15)'; // hsl(var(--primary) with opacity)
          overlayContext.fillRect(rectX, rectY, rectW, rectH);
          
          overlayContext.strokeStyle = 'rgba(59, 130, 246, 0.6)';
          overlayContext.lineWidth = 2;
          overlayContext.strokeRect(rectX, rectY, rectW, rectH);
        });
      });
    });

    return () => {
      active = false;
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
