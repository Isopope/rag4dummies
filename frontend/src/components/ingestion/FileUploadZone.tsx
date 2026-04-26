import { useRef, useCallback } from 'react';
import { Upload, File, CheckCircle2, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { UploadedFile } from '@/types/chat';
import type { DocumentItem } from '@/lib/api';

interface FileUploadZoneProps {
  files: UploadedFile[];
  documents: DocumentItem[];
  onUpload?: (file: File) => void;
  onDelete?: (sourcePath: string) => void;
}

const statusIcon: Record<string, React.FC<{ className?: string }>> = {
  indexed: CheckCircle2,
  processing: Loader2,
  uploading: Loader2,
  error: AlertCircle,
};

const statusLabel: Record<string, string> = {
  indexed: 'Indexé',
  processing: 'Traitement...',
  uploading: 'Upload...',
  error: 'Erreur',
};

const statusColor: Record<string, string> = {
  indexed: 'text-success',
  processing: 'text-info',
  uploading: 'text-primary',
  error: 'text-destructive',
};

const FileUploadZone = ({ files, documents, onUpload, onDelete }: FileUploadZoneProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  // Lookup rapide sourcePath par id
  const docById = Object.fromEntries(documents.map((d) => [d.id, d]));

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || !onUpload) return;
      Array.from(fileList).forEach((f) => onUpload(f));
    },
    [onUpload],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        className="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-primary/40 hover:bg-muted/30 transition-all cursor-pointer"
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
        <p className="text-sm font-medium text-foreground mb-1">Déposez vos fichiers ici</p>
        <p className="text-xs text-muted-foreground">PDF — jusqu'à 100 MB</p>
        <button
          type="button"
          className="mt-4 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
          onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
        >
          Parcourir les fichiers
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">Fichiers récents</h3>
          {files.map((file) => {
            const Icon = statusIcon[file.status];
            const doc = docById[file.id];
            return (
              <div key={file.id} className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card">
                <File className="w-8 h-8 text-primary/60 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-card-foreground truncate">{file.name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[11px] text-muted-foreground">{file.size}</span>
                    {doc?.error_message && (
                      <span className="text-[11px] text-destructive truncate max-w-[200px]" title={doc.error_message}>
                        {doc.error_message}
                      </span>
                    )}
                    {file.progress !== undefined && file.status !== 'indexed' && (
                      <div className="flex-1 max-w-[120px] h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${file.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                </div>
                <div className={`flex items-center gap-1.5 text-xs font-medium shrink-0 ${statusColor[file.status]}`}>
                  <Icon className={`w-3.5 h-3.5 ${file.status === 'processing' || file.status === 'uploading' ? 'animate-spin' : ''}`} />
                  {statusLabel[file.status]}
                </div>
                {onDelete && doc && (
                  <button
                    onClick={() => onDelete(doc.source_path)}
                    className="ml-1 p-1 rounded hover:bg-muted text-muted-foreground hover:text-destructive transition-colors"
                    title="Supprimer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default FileUploadZone;
