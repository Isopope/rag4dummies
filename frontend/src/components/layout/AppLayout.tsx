import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MessageSquare, Database, PanelLeftClose, PanelLeft, Moon, Sun, LogOut, UserCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';

interface AppLayoutProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  activeView: 'chat' | 'ingestion';
  onViewChange: (view: 'chat' | 'ingestion') => void;
}

const AppLayout = ({ sidebar, children, activeView, onViewChange }: AppLayoutProps) => {
  const { isAuthenticated, isAdmin, user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return document.documentElement.classList.contains('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  const NavButton = ({
    active,
    onClick,
    title,
    children: icon,
  }: {
    active: boolean;
    onClick: () => void;
    title: string;
    children: React.ReactNode;
  }) => (
    <button
      onClick={onClick}
      className={cn(
        'w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200',
        active
          ? 'bg-sidebar-accent text-sidebar-primary shadow-sm'
          : 'text-sidebar-foreground hover:bg-sidebar-accent/40 hover:text-sidebar-accent-foreground',
      )}
      title={title}
    >
      {icon}
    </button>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* ── Nav rail ────────────────────────────────────────────── */}
      <div className="shrink-0 w-14 bg-sidebar flex flex-col items-center py-3 gap-1 border-r border-sidebar-border">
        {/* Logo */}
        <div className="flex flex-col items-center mb-3 gap-0 select-none">
          <div className="flex items-baseline" style={{ gap: 0 }}>
            <span style={{ fontSize: 18, fontWeight: 900, color: '#fff', lineHeight: 1 }}>G</span>
            <span style={{ fontSize: 7, fontWeight: 900, color: '#fff', lineHeight: 1, position: 'relative', top: '-2px' }}>4</span>
            <span style={{ fontSize: 18, fontWeight: 900, color: '#e03120', lineHeight: 1 }}>AI</span>
          </div>
        </div>

        <NavButton active={activeView === 'chat'} onClick={() => onViewChange('chat')} title="Chat">
          <MessageSquare className="w-5 h-5" />
        </NavButton>

        {/* Ingestion : visible uniquement pour les administrateurs */}
        {isAdmin && (
          <NavButton active={activeView === 'ingestion'} onClick={() => onViewChange('ingestion')} title="Ingestion">
            <Database className="w-5 h-5" />
          </NavButton>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Dark mode toggle */}
        <button
          onClick={() => setDarkMode((d) => !d)}
          className="w-10 h-10 rounded-xl flex items-center justify-center text-sidebar-foreground hover:bg-sidebar-accent/40 transition-colors"
          title={darkMode ? 'Mode clair' : 'Mode sombre'}
        >
          {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* Sidebar toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="w-10 h-10 rounded-xl flex items-center justify-center text-sidebar-foreground hover:bg-sidebar-accent/40 transition-colors"
          title={sidebarOpen ? 'Masquer le panneau' : 'Afficher le panneau'}
        >
          {sidebarOpen ? <PanelLeftClose className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
        </button>

        {/* User controls */}
        {isAuthenticated ? (
          <div className="flex flex-col items-center gap-1 mt-1">
            {/* Avatar avec initiale */}
            <div
              className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-semibold cursor-default select-none"
              title={user?.email}
            >
              {user?.email?.[0]?.toUpperCase() ?? <UserCircle2 className="w-4 h-4" />}
            </div>
            {/* Bouton déconnexion */}
            <button
              onClick={() => { logout(); navigate('/'); }}
              className="w-10 h-9 rounded-xl flex items-center justify-center text-sidebar-foreground hover:bg-red-500/15 hover:text-red-400 transition-colors"
              title="Se déconnecter"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          /* Icône login quand non connecté */
          <button
            onClick={() => navigate('/login')}
            className="w-10 h-10 rounded-xl flex items-center justify-center text-sidebar-foreground hover:bg-sidebar-accent/40 transition-colors"
            title="Se connecter"
          >
            <UserCircle2 className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* ── Sidebar ────────────────────────────────────────────── */}
      {activeView === 'chat' && (
        <div
          className={cn(
            'shrink-0 border-r border-sidebar-border transition-all duration-300 overflow-hidden',
            sidebarOpen ? 'w-72' : 'w-0',
          )}
        >
          <div className="w-72 h-full">
            {sidebar}
          </div>
        </div>
      )}

      {/* ── Main content ───────────────────────────────────────── */}
      <div className="relative flex-1 flex flex-col min-w-0">
        {/* Topbar auth — flottant, visible uniquement quand non connecté */}
        {!isAuthenticated && (
          <div className="absolute top-3 right-4 z-20 flex items-center gap-2">
            <Link to="/login">
              <button className="h-8 px-4 rounded-full text-xs font-medium border border-border bg-background/80 backdrop-blur-sm text-foreground hover:bg-secondary/60 transition-colors shadow-sm">
                Se connecter
              </button>
            </Link>
            <Link to="/register">
              <button className="h-8 px-4 rounded-full text-xs font-medium bg-foreground text-background hover:opacity-90 transition-opacity shadow-sm">
                S'inscrire
              </button>
            </Link>
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

export default AppLayout;
