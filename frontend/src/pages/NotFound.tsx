import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background relative overflow-hidden">
      <div className="absolute inset-0 welcome-dot-grid opacity-50" />
      <div className="absolute inset-0 bg-gradient-to-b from-background/30 via-background/70 to-background pointer-events-none" />

      <div className="relative z-10 text-center px-8 space-y-6 max-w-md">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">Erreur 404</p>
        <h1 className="font-display text-[120px] font-light leading-none text-foreground tracking-tight">404</h1>
        <p className="font-display text-2xl font-light text-foreground">Page introuvable.</p>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Cette adresse ne mene nulle part. Retournez a votre espace documentaire.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Retour a l&apos;accueil
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
