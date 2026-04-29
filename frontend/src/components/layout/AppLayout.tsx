import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { AppView } from '@/types/layout';
import { MessageSquare, Database, PanelLeftClose, PanelLeft, Moon, Sun, LogOut, UserCircle2, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';

interface AppLayoutProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  activeView: AppView;
  onViewChange: (view: AppView) => void;
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
        <div className="flex flex-col items-center mb-3">
          <img src="/go4aiLogo.png" alt="Go4AI" className="h-7 w-auto" />
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

        {/* Admin : visible uniquement pour les administrateurs */}
        {isAdmin && (
          <NavButton active={activeView === 'admin'} onClick={() => onViewChange('admin')} title="Administration">
            <ShieldCheck className="w-5 h-5" />
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
              onClick={() => { logout(); navigate('/chat', { replace: true }); }}
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

      {/* ── Sidebar : uniquement en vue chat ──────────────────── */}
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

        {activeView === 'admin' && (
          <div className="shrink-0 border-b border-border bg-background/95 backdrop-blur-sm">
            <div className="flex items-center justify-between px-6 py-4">
              <div className="min-w-0">
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  Espace de travail / Administration
                </p>
                <div className="mt-2 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <h1 className="text-base font-semibold text-foreground">Administration</h1>
                    <p className="text-sm text-muted-foreground">
                      Gestion des entites et des parametres metier.
                    </p>
                  </div>
                </div>
              </div>

              <div className="hidden md:flex items-center rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                Vue admin active
              </div>
            </div>
          </div>
        )}

        {children}
      </div>
    </div>
  );
};

export default AppLayout;
