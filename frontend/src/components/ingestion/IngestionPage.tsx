import { Search } from 'lucide-react';
import ConnectorCard from './ConnectorCard';
import ConnectorModal from './ConnectorModal';
import FileUploadZone from './FileUploadZone';
import type { UploadedFile } from '@/types/chat';
import type { DocumentItem, DocumentListStats } from '@/lib/api';
import { useState } from 'react';
import { useConnectors, type ConnectorType, type CrawlBody } from '@/hooks/use-connectors';

interface IngestionPageProps {
  uploadingFiles: UploadedFile[];
  documents: DocumentItem[];
  documentStats: DocumentListStats;
  documentsTotal: number;
  documentsPageIndex: number;
  documentsPageCount: number;
  documentsPageSize: number;
  isDocumentsFetching?: boolean;
  onDocumentsPageChange: (pageIndex: number) => void;
  onDocumentsPageSizeChange: (pageSize: number) => void;
  onUpload?: (file: File, entity?: string, validityDate?: string) => void;
  onDeleteDocument?: (sourcePath: string) => void;
}

function docToUploadedFile(doc: DocumentItem): UploadedFile {
  const statusMap: Record<string, UploadedFile['status']> = {
    pending: 'processing',
    processing: 'processing',
    indexed: 'indexed',
    error: 'error',
  };

  return {
    id: doc.id,
    name: doc.filename,
    size: doc.chunk_count ? `${doc.chunk_count} chunks` : '-',
    type: 'application/pdf',
    status: statusMap[doc.status] ?? 'processing',
    progress: doc.status === 'indexed' ? 100 : doc.status === 'error' ? undefined : 50,
    uploadedAt: new Date(doc.created_at),
  };
}

const IngestionPage = ({
  uploadingFiles,
  documents,
  documentStats,
  documentsTotal,
  documentsPageIndex,
  documentsPageCount,
  documentsPageSize,
  isDocumentsFetching,
  onDocumentsPageChange,
  onDocumentsPageSizeChange,
  onUpload,
  onDeleteDocument,
}: IngestionPageProps) => {
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'connectors' | 'files'>('connectors');
  const [openModal, setOpenModal] = useState<ConnectorType | null>(null);

  const { connectors, launch } = useConnectors();

  const filteredConnectors = connectors.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()),
  );

  const activeConnectors = connectors.filter(
    (c) => c.status === 'connected' || c.status === 'syncing' || c.status === 'queued',
  ).length;

  const activeUploads = uploadingFiles.filter((file) => file.status === 'uploading');
  const pagedFiles = documents.map(docToUploadedFile);

  const handleLaunch = async (body: CrawlBody) => {
    if (!openModal) return;
    await launch(openModal, body);
    setOpenModal(null);
  };

  const launchingConnector = openModal ? connectors.find((c) => c.type === openModal) : null;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground">Ingestion des donnees</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Gerez vos sources de donnees et suivez l&apos;indexation de vos documents.
          </p>
        </div>

        <div className="mb-8 grid grid-cols-3 gap-4">
          {[
            { label: 'Connecteurs actifs', value: activeConnectors, total: connectors.length },
            { label: 'Chunks indexes', value: documentStats.total_chunks.toLocaleString() },
            { label: 'Documents indexes', value: documentStats.indexed_documents.toLocaleString() },
          ].map((stat, index) => (
            <div key={index} className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="mt-1 text-2xl font-bold text-card-foreground">
                {stat.value}
                {'total' in stat && (
                  <span className="text-sm font-normal text-muted-foreground">/{stat.total}</span>
                )}
              </p>
            </div>
          ))}
        </div>

        <div className="mb-6 flex items-center gap-6 border-b border-border">
          {[
            { id: 'connectors' as const, label: 'Connecteurs' },
            { id: 'files' as const, label: 'Fichiers' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-b-2 border-primary text-foreground'
                  : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
          <div className="flex-1" />
          {activeTab === 'connectors' && (
            <div className="flex items-center gap-2 pb-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Rechercher..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
          )}
        </div>

        {activeTab === 'connectors' ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredConnectors.map((connector) => (
              <ConnectorCard
                key={connector.type}
                connector={connector}
                onConfigure={setOpenModal}
              />
            ))}
          </div>
        ) : (
          <FileUploadZone
            uploadingFiles={activeUploads}
            recentFiles={pagedFiles}
            documents={documents}
            totalDocuments={documentsTotal}
            pageIndex={documentsPageIndex}
            pageCount={documentsPageCount}
            pageSize={documentsPageSize}
            isFetching={isDocumentsFetching}
            onPageChange={onDocumentsPageChange}
            onPageSizeChange={onDocumentsPageSizeChange}
            onUpload={onUpload}
            onDelete={onDeleteDocument}
          />
        )}
      </div>

      {openModal && (
        <ConnectorModal
          type={openModal}
          isLoading={launchingConnector?.isLaunching ?? false}
          onSubmit={handleLaunch}
          onClose={() => setOpenModal(null)}
        />
      )}
    </div>
  );
};

export default IngestionPage;
