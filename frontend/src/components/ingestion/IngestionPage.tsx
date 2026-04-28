import { Search } from 'lucide-react';
import ConnectorCard from './ConnectorCard';
import ConnectorModal from './ConnectorModal';
import FileUploadZone from './FileUploadZone';
import { UploadedFile } from '@/types/chat';
import type { DocumentItem } from '@/lib/api';
import { useState } from 'react';
import { useConnectors, type ConnectorType, type CrawlBody } from '@/hooks/use-connectors';

interface IngestionPageProps {
  uploadingFiles: UploadedFile[];
  documents: DocumentItem[];
  onUpload?: (file: File, entity?: string, validityDate?: string) => void;
  onDeleteDocument?: (sourcePath: string) => void;
}

/** Convertit un DocumentItem persisté en UploadedFile pour FileUploadZone. */
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
    size: doc.chunk_count ? `${doc.chunk_count} chunks` : '—',
    type: 'application/pdf',
    status: statusMap[doc.status] ?? 'processing',
    progress: doc.status === 'indexed' ? 100 : doc.status === 'error' ? undefined : 50,
    uploadedAt: new Date(doc.created_at),
  };
}

const IngestionPage = ({
  uploadingFiles,
  documents,
  onUpload,
  onDeleteDocument,
}: IngestionPageProps) => {
  const totalIndexedChunks = documents.reduce((sum, d) => sum + (d.chunk_count ?? 0), 0);
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

  // Fusionner les fichiers en cours d'upload (mémoire) avec les docs persistés (DB).
  const uploadingNames = new Set(
    uploadingFiles.filter((f) => f.status === 'uploading').map((f) => f.name),
  );
  const persistedFiles: UploadedFile[] = documents
    .filter((d) => !uploadingNames.has(d.filename))
    .map(docToUploadedFile);

  const mergedFiles: UploadedFile[] = [
    ...uploadingFiles.filter((f) => f.status === 'uploading'),
    ...persistedFiles,
  ];

  const handleLaunch = async (body: CrawlBody) => {
    if (!openModal) return;
    await launch(openModal, body);
    setOpenModal(null);
  };

  const launchingConnector = openModal ? connectors.find((c) => c.type === openModal) : null;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto py-8 px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground">Ingestion des données</h1>
          <p className="text-sm text-muted-foreground mt-1">Gérez vos sources de données et suivez l'indexation de vos documents.</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: 'Connecteurs actifs', value: activeConnectors, total: connectors.length },
            { label: 'Chunks indexés', value: totalIndexedChunks.toLocaleString() },
            { label: 'Documents indexés', value: documents.filter((d) => d.status === 'indexed').length },
          ].map((stat, i) => (
            <div key={i} className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold text-card-foreground mt-1">
                {stat.value}
                {'total' in stat && <span className="text-sm font-normal text-muted-foreground">/{stat.total}</span>}
              </p>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-6 border-b border-border mb-6">
          {[
            { id: 'connectors' as const, label: 'Connecteurs' },
            { id: 'files' as const, label: 'Fichiers' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
          <div className="flex-1" />
          {activeTab === 'connectors' && (
            <div className="flex items-center gap-2 pb-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Rechercher…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
          )}
        </div>

        {/* Content */}
        {activeTab === 'connectors' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
            files={mergedFiles}
            onUpload={onUpload}
            onDelete={onDeleteDocument}
            documents={documents}
          />
        )}
      </div>

      {/* Modal */}
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
