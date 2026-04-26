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
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4">
        {/* Header */}
        <div className="text-center">
          <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center mx-auto mb-4">
            <span className="text-primary-foreground font-bold text-lg">R</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground">Créer un compte</h1>
          <p className="text-sm text-muted-foreground mt-1">Commencez à explorer vos documents</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground" htmlFor="email">
              Adresse e-mail
            </label>
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
            <label className="text-sm font-medium text-foreground" htmlFor="password">
              Mot de passe
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="8 caractères minimum"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground" htmlFor="confirm">
              Confirmer le mot de passe
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? 'Création du compte...' : "S'inscrire"}
          </button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          Déjà un compte ?{' '}
          <Link to="/login" className="text-primary hover:underline">
            Se connecter
          </Link>
        </p>
      </div>
    </div>
  );
}
