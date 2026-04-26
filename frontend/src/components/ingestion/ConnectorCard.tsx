import { Connector, ConnectorStatus } from '@/types/chat';
import { HardDrive, BookOpen, MessageSquare, Github, FileText, Database, RefreshCw, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

const iconMap: Record<string, React.FC<{ className?: string }>> = {
  HardDrive, BookOpen, MessageSquare, Github, FileText, Database,
};

const statusConfig: Record<ConnectorStatus, { label: string; color: string; icon: React.FC<{ className?: string }> }> = {
  connected: { label: 'Connecté', color: 'text-success', icon: CheckCircle2 },
  syncing: { label: 'Synchronisation...', color: 'text-info', icon: Loader2 },
  error: { label: 'Erreur', color: 'text-destructive', icon: AlertCircle },
  disconnected: { label: 'Déconnecté', color: 'text-muted-foreground', icon: AlertCircle },
};

interface ConnectorCardProps {
  connector: Connector;
}

const ConnectorCard = ({ connector }: ConnectorCardProps) => {
  const IconComponent = iconMap[connector.icon] || FileText;
  const status = statusConfig[connector.status];
  const StatusIcon = status.icon;

  const formatTime = (date?: Date) => {
    if (!date) return 'Jamais';
    const diff = Date.now() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `Il y a ${minutes}min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Il y a ${hours}h`;
    return `Il y a ${Math.floor(hours / 24)}j`;
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 hover:bg-connector-card-hover hover:shadow-sm transition-all group">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <IconComponent className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-card-foreground">{connector.name}</h3>
            <p className="text-xs text-muted-foreground">{connector.description}</p>
          </div>
        </div>
        {connector.status === 'connected' && (
          <button className="opacity-0 group-hover:opacity-100 p-1.5 rounded-md hover:bg-muted transition-all">
            <RefreshCw className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        )}
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          {connector.documentsCount > 0 && (
            <span>{connector.documentsCount.toLocaleString()} docs</span>
          )}
          {connector.lastSync && (
            <span>Sync: {formatTime(connector.lastSync)}</span>
          )}
        </div>
        <div className={`flex items-center gap-1.5 text-xs font-medium ${status.color}`}>
          <StatusIcon className={`w-3.5 h-3.5 ${connector.status === 'syncing' ? 'animate-spin' : ''}`} />
          {status.label}
        </div>
      </div>
    </div>
  );
};

export default ConnectorCard;
