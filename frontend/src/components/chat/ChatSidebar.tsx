import { Plus, MessageSquare, Search, Pencil } from 'lucide-react';
import { ChatSession } from '@/types/chat';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
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

const ChatSidebar = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  folded,
}: ChatSidebarProps) => {
  const [search, setSearch] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase()),
  );

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
      {/* Header: New session button */}
      <div className="p-3 border-b border-sidebar-border">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-sidebar-accent text-sidebar-accent-foreground hover:bg-sidebar-muted transition-colors text-sm font-medium"
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

      {/* Section: Recents */}
      <div className="px-3 pt-1 pb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40 px-1">
          Récents
        </span>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-2">
        {filtered.length === 0 ? (
          <p className="text-xs text-sidebar-foreground/40 px-2 py-4 text-center">
            {search ? 'Aucun résultat' : 'Envoyez un message pour commencer !'}
          </p>
        ) : (
          filtered.map((session) => (
            <button
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={cn(
                'w-full text-left px-3 py-2.5 rounded-xl mb-0.5 transition-colors group',
                session.id === activeSessionId
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'hover:bg-sidebar-accent/40 text-sidebar-foreground',
              )}
            >
              <div className="flex items-start gap-2.5">
                <MessageSquare className="w-4 h-4 mt-0.5 shrink-0 opacity-40" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">{session.title}</span>
                    <span className="text-[10px] opacity-40 shrink-0 tabular-nums">
                      {formatTime(session.timestamp)}
                    </span>
                  </div>
                  {session.lastMessage && (
                    <p className="text-xs opacity-40 truncate mt-0.5">{session.lastMessage}</p>
                  )}
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default ChatSidebar;
