import { Plus, Search } from 'lucide-react';
import ConnectorCard from './ConnectorCard';
import FileUploadZone from './FileUploadZone';
import { Connector, UploadedFile } from '@/types/chat';
import { useState } from 'react';

interface IngestionPageProps {
  connectors: Connector[];
  files: UploadedFile[];
  onUpload?: (file: File) => void;
  totalIndexedChunks?: number;
}

const IngestionPage = ({ connectors, files, onUpload, totalIndexedChunks = 0 }: IngestionPageProps) => {
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'connectors' | 'files'>('connectors');

  const filteredConnectors = connectors.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const totalDocs = connectors.reduce((sum, c) => sum + c.documentsCount, 0);
  const activeConnectors = connectors.filter(c => c.status === 'connected' || c.status === 'syncing').length;

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
            { label: 'Fichiers uploadés', value: files.length },
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
                  placeholder="Rechercher..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
                <Plus className="w-3.5 h-3.5" />
                Ajouter
              </button>
            </div>
          )}
        </div>

        {/* Content */}
        {activeTab === 'connectors' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredConnectors.map((connector) => (
              <ConnectorCard key={connector.id} connector={connector} />
            ))}
          </div>
        ) : (
          <FileUploadZone files={files} onUpload={onUpload} />
        )}
      </div>
    </div>
  );
};

export default IngestionPage;
