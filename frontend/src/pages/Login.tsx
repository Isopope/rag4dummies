import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

const BRAND_BLUE = '#1e3a8a';
const BRAND_RED  = '#e03120';

function Go4AILogo({ size = 48 }: { size?: number }) {
  return (
    <div className="flex items-baseline select-none" style={{ gap: 0 }}>
      <span style={{ fontSize: size, fontWeight: 900, color: BRAND_BLUE, fontFamily: 'Inter, sans-serif', lineHeight: 1 }}>G</span>
      <span style={{ fontSize: size * 0.38, fontWeight: 900, color: BRAND_BLUE, fontFamily: 'Inter, sans-serif', lineHeight: 1, position: 'relative', top: '-0.05em' }}>4</span>
      <span style={{ fontSize: size, fontWeight: 900, color: BRAND_RED, fontFamily: 'Inter, sans-serif', lineHeight: 1 }}>AI</span>
    </div>
  );
}

export default function Login() {
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const { login }               = useAuth();
  const navigate                = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Identifiants invalides');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* ── Panneau gauche — branding ───────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[45%] px-16 py-14"
        style={{ background: `linear-gradient(150deg, ${BRAND_BLUE} 0%, #0f2050 100%)` }}
      >
        {/* Logo */}
        <div>
          <div className="flex items-baseline select-none gap-0">
            <span style={{ fontSize: 44, fontWeight: 900, color: '#fff', lineHeight: 1 }}>G</span>
            <span style={{ fontSize: 16, fontWeight: 900, color: '#fff', lineHeight: 1, position: 'relative', top: '-4px' }}>4</span>
            <span style={{ fontSize: 44, fontWeight: 900, color: BRAND_RED, lineHeight: 1 }}>AI</span>
          </div>
          <p className="text-white/50 text-sm mt-1 tracking-wide">Gouvernance 4 AI</p>
        </div>

        {/* Tagline centrale */}
        <div className="space-y-5">
          <p className="text-white/20 text-xs uppercase tracking-[0.2em] font-semibold">Plateforme RAG</p>
          <h2 className="text-white text-4xl font-extrabold leading-tight">
            Exploitez
            <br />
            l'intelligence
            <br />
            de vos documents.
          </h2>
          <p className="text-white/50 text-sm leading-relaxed max-w-xs">
            Indexez, interrogez et analysez vos données internes avec un assistant IA souverain.
          </p>
        </div>

        {/* Footer */}
        <p className="text-white/25 text-xs">© 2026 Go4AI — Tous droits réservés</p>
      </div>

      {/* ── Panneau droit — formulaire ──────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-background px-8">
        <div className="w-full max-w-sm space-y-8">
          {/* Logo mobile */}
          <div className="lg:hidden flex justify-center">
            <Go4AILogo size={40} />
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Connexion</h1>
            <p className="text-sm text-muted-foreground mt-1">Accédez à votre espace documentaire</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="vous@exemple.com"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="password">Mot de passe</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-50"
              style={{ background: `linear-gradient(90deg, ${BRAND_BLUE} 0%, #2451b3 100%)` }}
            >
              {loading ? 'Connexion...' : 'Se connecter'}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Pas encore de compte ?{' '}
            <Link to="/register" className="font-semibold" style={{ color: BRAND_RED }}>Créer un compte</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
