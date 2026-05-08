import { useState } from 'react';
import { Trash2, Plus, Loader2 } from 'lucide-react';
import { useEntities } from '@/hooks/use-entities';

export default function Admin() {
  const { entities, isLoading, create, remove } = useEntities();
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    await create(name);
    setNewName('');
    setCreating(false);
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 max-w-2xl mx-auto w-full">
      <div className="mb-8">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground mb-2">Configuration</p>
        <h1 className="font-display text-3xl font-light text-foreground tracking-tight">Entites</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Definissez les proprietaires logiques rattaches a vos documents.
        </p>
      </div>

      {/* Create entity form */}
      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Nom de la nouvelle entite"
          required
          className="flex-1 px-3.5 py-2.5 text-sm border border-border rounded-xl bg-card focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-colors"
        />
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-60 transition-opacity shadow-sm"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Creer
        </button>
      </form>

      {/* Entity list */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {entities.length} entite{entities.length > 1 ? 's' : ''}
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : entities.length === 0 ? (
          <div className="py-16 text-center text-sm text-muted-foreground">
            Aucune entite creee pour l&apos;instant.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {entities.map((entity) => (
              <li key={entity.id} className="flex items-center px-4 py-3 gap-3 hover:bg-muted/20 transition-colors">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-card-foreground">{entity.name}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Creee le {new Date(entity.created_at).toLocaleDateString('fr-FR')}
                  </p>
                </div>
                <button
                  onClick={() => remove(entity.id, entity.name)}
                  aria-label={`Supprimer l'entite ${entity.name}`}
                  className="p-1.5 rounded-lg text-muted-foreground hover:bg-red-500/10 hover:text-red-500 transition-colors"
                  title={`Supprimer « ${entity.name} »`}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
