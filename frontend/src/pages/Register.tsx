import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '@/lib/api';
import { toast } from 'sonner';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error('Les mots de passe ne correspondent pas.');
      return;
    }
    if (password.length < 8) {
      toast.error('Le mot de passe doit contenir au moins 8 caractères.');
      return;
    }
    setLoading(true);
    try {
      await register(email, password);
      toast.success('Compte créé ! Vous pouvez maintenant vous connecter.');
      navigate('/login');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erreur lors de la création du compte.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* ── Left panel — branding ─────────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[45%] px-16 py-14 relative overflow-hidden"
        style={{ background: 'linear-gradient(150deg, hsl(234 68% 20%) 0%, hsl(235 72% 10%) 100%)' }}
      >
        {/* Subtle dot grid texture */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.035) 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        />

        {/* Logo */}
        <div className="relative z-10">
          <img src="/go4aiLogo.png" alt="Go4AI" className="h-9 w-auto" />
          <p className="text-white/35 text-xs mt-2 tracking-[0.18em] uppercase font-medium">Gouvernance 4 AI</p>
        </div>

        {/* Central content */}
        <div className="relative z-10 space-y-8">
          <p className="text-white/25 text-[10px] uppercase tracking-[0.28em] font-semibold">Rejoindre la plateforme</p>

          <h2 className="font-display font-light text-white text-5xl leading-[1.05] tracking-tight">
            Créez votre<br />
            espace<br />
            <em className="not-italic" style={{ color: 'hsl(20, 96%, 58%)' }}>documentaire</em><br />
            souverain.
          </h2>

          {/* Document stack illustration */}
          <svg viewBox="0 0 280 180" fill="none" className="w-64 opacity-90" aria-hidden="true">
            <g transform="rotate(-10 140 90)">
              <rect x="40" y="10" width="140" height="180" rx="6" fill="white" fillOpacity="0.02" stroke="white" strokeOpacity="0.06"/>
            </g>
            <g transform="rotate(-4 140 90)">
              <rect x="40" y="10" width="140" height="180" rx="6" fill="white" fillOpacity="0.03" stroke="white" strokeOpacity="0.09"/>
            </g>
            <rect x="40" y="10" width="140" height="180" rx="6" fill="white" fillOpacity="0.05" stroke="white" strokeOpacity="0.14"/>
            <line x1="60" y1="44" x2="160" y2="44" stroke="white" strokeOpacity="0.14" strokeWidth="1"/>
            <line x1="60" y1="60" x2="148" y2="60" stroke="white" strokeOpacity="0.09" strokeWidth="1"/>
            <line x1="60" y1="76" x2="155" y2="76" stroke="white" strokeOpacity="0.07" strokeWidth="1"/>
            <line x1="60" y1="92" x2="130" y2="92" stroke="white" strokeOpacity="0.07" strokeWidth="1"/>
            <circle cx="60" cy="44" r="2.5" fill="hsl(20,96%,58%)" fillOpacity="0.9"/>
            <circle cx="222" cy="50" r="32" fill="none" stroke="white" strokeOpacity="0.06"/>
            <circle cx="222" cy="50" r="16" fill="none" stroke="white" strokeOpacity="0.09"/>
            <circle cx="222" cy="50" r="4" fill="white" fillOpacity="0.25"/>
            <line x1="62" y1="42" x2="218" y2="50" stroke="white" strokeOpacity="0.06" strokeWidth="0.5" strokeDasharray="4 3"/>
          </svg>

          <p className="text-white/35 text-sm leading-relaxed max-w-[260px]">
            Importez vos fichiers et posez des questions sur vos contenus en quelques secondes.
          </p>
        </div>

        {/* Footer */}
        <div className="relative z-10 flex items-center gap-3">
          <img src="/aghadoeLogo.png" alt="Aghadoe" className="h-5 w-auto opacity-30" />
          <p className="text-white/20 text-xs">© 2026 Aghadoe — Tous droits réservés</p>
        </div>
      </div>

      {/* ── Right panel — form ────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-background px-8">
        <div className="w-full max-w-sm space-y-10">
          {/* Mobile logo */}
          <div className="lg:hidden flex justify-center">
            <img src="/go4aiLogo.png" alt="Go4AI" className="h-10 w-auto" />
          </div>

          {/* Heading */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground mb-2">Créer un accès</p>
            <h1 className="font-display text-4xl font-light text-foreground tracking-tight">Inscription</h1>
            <p className="text-sm text-muted-foreground mt-1.5">Commencez à explorer vos documents</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-7">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground" htmlFor="email">
                Adresse e-mail
              </label>
              <input
                id="email" type="email" autoComplete="email" required
                value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full py-2.5 bg-transparent border-0 border-b-2 border-border text-sm focus:outline-none focus:border-primary transition-colors placeholder:text-muted-foreground/40"
                placeholder="vous@exemple.com"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground" htmlFor="password">
                Mot de passe
              </label>
              <input
                id="password" type="password" autoComplete="new-password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full py-2.5 bg-transparent border-0 border-b-2 border-border text-sm focus:outline-none focus:border-primary transition-colors placeholder:text-muted-foreground/40"
                placeholder="8 caractères minimum"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground" htmlFor="confirm">
                Confirmer le mot de passe
              </label>
              <input
                id="confirm" type="password" autoComplete="new-password" required
                value={confirm} onChange={(e) => setConfirm(e.target.value)}
                className="w-full py-2.5 bg-transparent border-0 border-b-2 border-border text-sm focus:outline-none focus:border-primary transition-colors placeholder:text-muted-foreground/40"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold text-white bg-primary hover:opacity-90 transition-opacity disabled:opacity-50 shadow-sm"
            >
              {loading ? 'Création du compte…' : "S'inscrire"}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Déjà un compte ?{' '}
            <Link to="/login" className="font-semibold text-accent hover:opacity-75 transition-opacity">
              Se connecter
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
