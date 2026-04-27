import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '@/lib/api';
import { toast } from 'sonner';

const BRAND_BLUE   = '#384596';
const BRAND_ORANGE = '#F45A00';

export default function Register() {
  const [email, setEmail]     = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [loading, setLoading]   = useState(false);
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
      {/* ── Panneau gauche — branding ───────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[45%] px-16 py-14"
        style={{ background: `linear-gradient(150deg, ${BRAND_BLUE} 0%, #1f2d72 100%)` }}
      >
        <div>
          <img src="/go4aiLogo.png" alt="Go4AI" className="h-10 w-auto" />
          <p className="text-white/50 text-sm mt-2 tracking-wide">Gouvernance 4 AI</p>
        </div>

        <div className="space-y-5">
          <p className="text-white/20 text-xs uppercase tracking-[0.2em] font-semibold">Rejoindre la plateforme</p>
          <h2 className="text-white text-4xl font-extrabold leading-tight">
            Créez votre
            <br />
            espace
            <br />
            documentaire.
          </h2>
          <p className="text-white/50 text-sm leading-relaxed max-w-xs">
            Importez vos fichiers et posez des questions sur vos contenus en quelques secondes.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <img src="/aghadoeLogo.png" alt="Aghadoe" className="h-6 w-auto opacity-50" />
          <p className="text-white/25 text-xs">© 2026 Aghadoe — Tous droits réservés</p>
        </div>
      </div>

      {/* ── Panneau droit — formulaire ──────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-background px-8">
        <div className="w-full max-w-sm space-y-8">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Créer un compte</h1>
            <p className="text-sm text-muted-foreground mt-1">Commencez à explorer vos documents</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="email">Adresse e-mail</label>
              <input
                id="email" type="email" autoComplete="email" required
                value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="vous@exemple.com"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="password">Mot de passe</label>
              <input
                id="password" type="password" autoComplete="new-password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="8 caractères minimum"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="confirm">Confirmer le mot de passe</label>
              <input
                id="confirm" type="password" autoComplete="new-password" required
                value={confirm} onChange={(e) => setConfirm(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-50"
              style={{ background: `linear-gradient(90deg, ${BRAND_BLUE} 0%, #4a5cb8 100%)` }}
            >
              {loading ? 'Création du compte...' : "S'inscrire"}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Déjà un compte ?{' '}
            <Link to="/login" className="font-semibold" style={{ color: BRAND_ORANGE }}>Se connecter</Link>
          </p>
        </div>
      </div>
    </div>
  );
}