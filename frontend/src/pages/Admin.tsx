import { useState } from 'react';
import { Trash2, Plus, Loader2, ShieldCheck } from 'lucide-react';
import { useEntities } from '@/hooks/use-entities';
import AppLayout from '@/components/layout/AppLayout';

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
      <div className="flex items-center gap-3 mb-8">
        <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center">
          <ShieldCheck className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Administration</h1>
          <p className="text-sm text-muted-foreground">Gestion des entités (propriétaires de documents)</p>
        </div>
      </div>

      {/* Create entity form */}
      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Nom de la nouvelle entité"
          required
          className="flex-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-60 transition-opacity"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Créer
        </button>
      </form>

      {/* Entity list */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30">
          <h2 className="text-sm font-semibold text-foreground">
            Entités ({entities.length})
          </h2>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : entities.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Aucune entité créée pour l'instant.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {entities.map((entity) => (
              <li key={entity.id} className="flex items-center px-4 py-3 gap-3 hover:bg-muted/20 transition-colors">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-card-foreground">{entity.name}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Créée le {new Date(entity.created_at).toLocaleDateString('fr-FR')}
                  </p>
                </div>
                <button
                  onClick={() => remove(entity.id, entity.name)}
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

/** Wraps Admin with AppLayout for navigation */
export function AdminPage() {
  return (
    <AppLayout
      sidebar={null}
      activeView="chat"
      onViewChange={() => {}}
    >
      <Admin />
    </AppLayout>
  );
}
