import { Plus, MessageSquare, Search, Pencil, Trash2, Check, X } from 'lucide-react';
import { ChatSession } from '@/types/chat';
import { useState, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession?: (id: string) => void;
  onRenameSession?: (id: string, title: string) => void;
  folded?: boolean;
}

const formatTime = (date: Date) => {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'À l\'instant';
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}j`;
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
};

interface SessionGroup {
  label: string;
  items: ChatSession[];
}

function groupByPeriod(sessions: ChatSession[]): SessionGroup[] {
  const now = new Date();
  const startOfToday    = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86_400_000);
  const startOfWeek     = new Date(startOfToday.getTime() - 7  * 86_400_000);
  const startOfMonth    = new Date(startOfToday.getTime() - 30 * 86_400_000);

  const buckets: Record<string, ChatSession[]> = {
    "Aujourd'hui":  [],
    'Hier':         [],
    'Cette semaine': [],
    'Ce mois-ci':   [],
    'Plus ancien':  [],
  };

  for (const s of sessions) {
    const d = new Date(s.timestamp);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if      (day >= startOfToday)    buckets["Aujourd'hui"].push(s);
    else if (day >= startOfYesterday) buckets['Hier'].push(s);
    else if (day >= startOfWeek)     buckets['Cette semaine'].push(s);
    else if (day >= startOfMonth)    buckets['Ce mois-ci'].push(s);
    else                             buckets['Plus ancien'].push(s);
  }

  return Object.entries(buckets)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}

// ── Session row ────────────────────────────────────────────────────────────────

interface SessionRowProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete?: () => void;
  onRename?: (newTitle: string) => void;
}

const SessionRow = ({ session, isActive, onSelect, onDelete, onRename }: SessionRowProps) => {
  const [isRenaming, setIsRenaming]   = useState(false);
  const [draftTitle, setDraftTitle]   = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const startRename = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setDraftTitle(session.title);
    setIsRenaming(true);
    // focus on next tick after render
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [session.title]);

  const commitRename = useCallback(() => {
    const trimmed = draftTitle.trim();
    if (trimmed && trimmed !== session.title) {
      onRename?.(trimmed);
    }
    setIsRenaming(false);
  }, [draftTitle, session.title, onRename]);

  const cancelRename = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation();
    setIsRenaming(false);
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter')  { e.preventDefault(); commitRename(); }
    if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
  }, [commitRename, cancelRename]);

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.();
  }, [onDelete]);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={isRenaming ? undefined : onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' && !isRenaming) onSelect(); }}
      className={cn(
        'group w-full text-left px-3 py-2.5 rounded-xl mb-0.5 transition-colors cursor-pointer select-none',
        isActive
          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
          : 'hover:bg-sidebar-accent/40 text-sidebar-foreground',
      )}
    >
      <div className="flex items-start gap-2.5">
        <MessageSquare className="w-4 h-4 mt-0.5 shrink-0 opacity-40" />
        <div className="flex-1 min-w-0">

          {/* Title row */}
          <div className="flex items-center justify-between gap-1">
            {isRenaming ? (
              <input
                ref={inputRef}
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                onBlur={commitRename}
                onKeyDown={handleKeyDown}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 min-w-0 text-sm bg-transparent border-b border-sidebar-ring outline-none"
              />
            ) : (
              <span className="flex-1 text-sm font-medium truncate">{session.title}</span>
            )}

            {/* Timestamp / actions */}
            {isRenaming ? (
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={(e) => { e.stopPropagation(); commitRename(); }} className="p-0.5 rounded hover:text-green-500">
                  <Check className="w-3.5 h-3.5" />
                </button>
                <button onClick={cancelRename} className="p-0.5 rounded hover:text-red-500">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-0.5 shrink-0">
                {/* Timestamp hidden on hover when actions visible */}
                <span className="text-[10px] opacity-40 tabular-nums group-hover:hidden">
                  {formatTime(session.timestamp)}
                </span>
                {/* Action buttons visible on hover */}
                <div className="hidden group-hover:flex items-center gap-0.5">
                  {onRename && (
                    <button
                      onClick={startRename}
                      title="Renommer"
                      className="p-0.5 rounded opacity-50 hover:opacity-100 transition-opacity"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                  )}
                  {onDelete && (
                    <button
                      onClick={handleDelete}
                      title="Supprimer"
                      className="p-0.5 rounded opacity-50 hover:opacity-100 hover:text-red-500 transition-opacity"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Last message excerpt */}
          {!isRenaming && session.lastMessage && (
            <p className="text-xs opacity-40 truncate mt-0.5">{session.lastMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Main sidebar ───────────────────────────────────────────────────────────────

const ChatSidebar = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onRenameSession,
  folded,
}: ChatSidebarProps) => {
  const [search, setSearch] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase()),
  );

  const groups = search ? [{ label: 'Résultats', items: filtered }] : groupByPeriod(filtered);

  if (folded) {
    return (
      <div className="flex flex-col items-center py-3 gap-2">
        <button
          onClick={onNewSession}
          className="w-9 h-9 rounded-lg bg-sidebar-accent text-sidebar-accent-foreground hover:bg-sidebar-muted flex items-center justify-center transition-colors"
          title="Nouvelle conversation"
        >
          <Pencil className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-sidebar text-sidebar-foreground">
      {/* Header */}
      <div className="p-3 border-b border-sidebar-border">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-white hover:opacity-90 transition-opacity text-sm font-semibold shadow-sm"
          style={{ background: 'linear-gradient(90deg, #384596 0%, #4a5cb8 100%)' }}
        >
          <Pencil className="w-4 h-4" />
          Nouvelle conversation
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2.5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-sidebar-foreground/40" />
          <input
            type="text"
            placeholder="Rechercher…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-sidebar-accent border-none text-sm text-sidebar-accent-foreground placeholder:text-sidebar-foreground/35 focus:outline-none focus:ring-1 focus:ring-sidebar-ring"
          />
        </div>
      </div>

      {/* Sessions grouped */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-2">
        {groups.length === 0 ? (
          <p className="text-xs text-sidebar-foreground/40 px-2 py-4 text-center">
            {search ? 'Aucun résultat' : 'Envoyez un message pour commencer !'}
          </p>
        ) : (
          groups.map(({ label, items }) => (
            <div key={label}>
              <div className="px-1 pt-3 pb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                  {label}
                </span>
              </div>
              {items.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  isActive={session.id === activeSessionId}
                  onSelect={() => onSelectSession(session.id)}
                  onDelete={onDeleteSession ? () => onDeleteSession(session.id) : undefined}
                  onRename={onRenameSession ? (title) => onRenameSession(session.id, title) : undefined}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ChatSidebar;


