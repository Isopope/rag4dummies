import { HardDrive, Globe, Cloud, RefreshCw, AlertCircle, CheckCircle2, Loader2, Clock, Settings } from 'lucide-react';
import type { ConnectorCardState, ConnectorStatus, ConnectorType } from '@/hooks/use-connectors';

const iconMap: Record<ConnectorType, React.FC<{ className?: string }>> = {
  local: HardDrive,
  web: Globe,
  sharepoint: Cloud,
};

const statusConfig: Record<ConnectorStatus, { label: string; color: string; icon: React.FC<{ className?: string }> }> = {
  idle: { label: 'Non configuré', color: 'text-muted-foreground', icon: Clock },
  queued: { label: 'En attente', color: 'text-info', icon: Loader2 },
  syncing: { label: 'En cours…', color: 'text-info', icon: Loader2 },
  connected: { label: 'Indexé', color: 'text-success', icon: CheckCircle2 },
  error: { label: 'Erreur', color: 'text-destructive', icon: AlertCircle },
};

interface ConnectorCardProps {
  connector: ConnectorCardState;
  onConfigure: (type: ConnectorType) => void;
}

const ConnectorCard = ({ connector, onConfigure }: ConnectorCardProps) => {
  const IconComponent = iconMap[connector.type];
  const status = statusConfig[connector.status];
  const StatusIcon = status.icon;
  const isRunning = connector.status === 'syncing' || connector.status === 'queued';

  const formatTime = (iso?: string | null) => {
    if (!iso) return null;
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'à l\'instant';
    if (minutes < 60) return `il y a ${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `il y a ${hours} h`;
    return `il y a ${Math.floor(hours / 24)} j`;
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
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {isRunning && (
            <div className="p-1.5 rounded-md">
              <RefreshCw className="w-3.5 h-3.5 text-info animate-spin" />
            </div>
          )}
          <button
            onClick={() => onConfigure(connector.type)}
            disabled={connector.isLaunching}
            className="p-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
            title="Configurer et lancer"
          >
            <Settings className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-muted-foreground min-w-0">
          {connector.lastLaunchedAt && (
            <span className="truncate">Dernier lancement : {formatTime(connector.lastLaunchedAt)}</span>
          )}
          {connector.lastMessage && connector.status === 'error' && (
            <span className="text-destructive truncate max-w-[160px]" title={connector.lastMessage}>
              {connector.lastMessage}
            </span>
          )}
        </div>
        <div className={`flex items-center gap-1.5 text-xs font-medium shrink-0 ml-2 ${status.color}`}>
          <StatusIcon className={`w-3.5 h-3.5 ${isRunning ? 'animate-spin' : ''}`} />
          {status.label}
        </div>
      </div>

      {/* Bouton principal visible en idle ou après erreur */}
      {(connector.status === 'idle' || connector.status === 'error') && (
        <button
          onClick={() => onConfigure(connector.type)}
          disabled={connector.isLaunching}
          className="mt-4 w-full py-1.5 rounded-lg border border-dashed border-border text-xs text-muted-foreground hover:border-primary hover:text-primary transition-colors disabled:opacity-50"
        >
          {connector.status === 'idle' ? '+ Configurer' : 'Reconfigurer et relancer'}
        </button>
      )}
    </div>
  );
};

export default ConnectorCard;
