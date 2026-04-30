import { useRef, useCallback, useState, type DragEvent } from 'react';
import { Upload, File, CheckCircle2, Loader2, AlertCircle, Trash2, type LucideIcon } from 'lucide-react';
import type { UploadedFile } from '@/types/chat';
import type { DocumentItem } from '@/lib/api';
import { useEntities } from '@/hooks/use-entities';
import { TablePagination } from '@/components/ui/table-pagination';

interface FileUploadZoneProps {
  uploadingFiles: UploadedFile[];
  recentFiles: UploadedFile[];
  documents: DocumentItem[];
  totalDocuments: number;
  pageIndex: number;
  pageCount: number;
  pageSize: number;
  isFetching?: boolean;
  onPageChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onUpload?: (file: File, entity?: string, validityDate?: string) => void;
  onDelete?: (sourcePath: string) => void;
}

const statusIcon: Record<string, LucideIcon> = {
  indexed: CheckCircle2,
  processing: Loader2,
  uploading: Loader2,
  error: AlertCircle,
};

const statusLabel: Record<string, string> = {
  indexed: 'Indexe',
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

function FileRow({
  file,
  sourcePath,
  errorMessage,
  onDelete,
}: {
  file: UploadedFile;
  sourcePath?: string;
  errorMessage?: string | null;
  onDelete?: (sourcePath: string) => void;
}) {
  const Icon = statusIcon[file.status];

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-3">
      <File className="h-8 w-8 shrink-0 text-primary/60" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-card-foreground">{file.name}</p>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground">{file.size}</span>
          {errorMessage && (
            <span className="max-w-[200px] truncate text-[11px] text-destructive" title={errorMessage}>
              {errorMessage}
            </span>
          )}
          {file.progress !== undefined && file.status !== 'indexed' && (
            <div className="h-1.5 max-w-[120px] flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${file.progress}%` }}
              />
            </div>
          )}
        </div>
      </div>
      <div className={`flex shrink-0 items-center gap-1.5 text-xs font-medium ${statusColor[file.status]}`}>
        <Icon className={`h-3.5 w-3.5 ${file.status === 'processing' || file.status === 'uploading' ? 'animate-spin' : ''}`} />
        {statusLabel[file.status]}
      </div>
      {onDelete && sourcePath && (
        <button
          onClick={() => onDelete(sourcePath)}
          className="ml-1 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
          title="Supprimer"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

const FileUploadZone = ({
  uploadingFiles,
  recentFiles,
  documents,
  totalDocuments,
  pageIndex,
  pageCount,
  pageSize,
  isFetching,
  onPageChange,
  onPageSizeChange,
  onUpload,
  onDelete,
}: FileUploadZoneProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const { entities } = useEntities();
  const [selectedEntity, setSelectedEntity] = useState('');
  const [validityDate, setValidityDate] = useState('');
  const docById = Object.fromEntries(documents.map((document) => [document.id, document]));

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || !onUpload) return;
      Array.from(fileList).forEach((file) =>
        onUpload(file, selectedEntity || undefined, validityDate || undefined),
      );
    },
    [onUpload, selectedEntity, validityDate],
  );

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Entite (proprietaire)</label>
          <select
            value={selectedEntity}
            onChange={(e) => setSelectedEntity(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">- Aucune -</option>
            {entities.map((entity) => (
              <option key={entity.id} value={entity.name}>{entity.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Date d&apos;expiration</label>
          <input
            type="date"
            value={validityDate}
            onChange={(e) => setValidityDate(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      <div
        className="cursor-pointer rounded-xl border-2 border-dashed border-border p-8 text-center transition-all hover:border-primary/40 hover:bg-muted/30"
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
        <p className="mb-1 text-sm font-medium text-foreground">Deposez vos fichiers ici</p>
        <p className="text-xs text-muted-foreground">PDF - jusqu&apos;a 100 MB</p>
        <button
          type="button"
          className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
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

      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">Televersements en cours</h3>
          {uploadingFiles.map((file) => (
            <FileRow key={file.id} file={file} />
          ))}
        </div>
      )}

      {(recentFiles.length > 0 || totalDocuments > 0) && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Fichiers recents</h3>
              <p className="text-xs text-muted-foreground">
                {totalDocuments.toLocaleString()} document{totalDocuments > 1 ? 's' : ''} en base
              </p>
            </div>
            {isFetching && (
              <span className="text-xs text-muted-foreground">Mise a jour...</span>
            )}
          </div>

          {recentFiles.length > 0 ? (
            recentFiles.map((file) => {
              const doc = docById[file.id];
              return (
                <FileRow
                  key={file.id}
                  file={file}
                  sourcePath={doc?.source_path}
                  errorMessage={doc?.error_message}
                  onDelete={onDelete}
                />
              );
            })
          ) : (
            <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-6 text-sm text-muted-foreground">
              Aucun document sur cette page.
            </div>
          )}

          <TablePagination
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            totalRows={totalDocuments}
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
          />
        </div>
      )}
    </div>
  );
};

export default FileUploadZone;
