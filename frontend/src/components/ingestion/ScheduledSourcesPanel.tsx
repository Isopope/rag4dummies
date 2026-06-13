/**
 * ScheduledSourcesPanel — gestion des sources SharePoint synchronisées
 * périodiquement (pull planifié). Liste, création/édition, toggle, Sync now,
 * suppression. Autonome (utilise useConnectorConfigs).
 */
import { useState } from 'react';
import { Plus, RefreshCw, Trash2, Pencil } from 'lucide-react';
import { useConnectorConfigs } from '@/hooks/use-connector-configs';
import type { ConnectorConfigItem, ConnectorConfigPayload } from '@/lib/api';

const DAY = 86400;

interface FormState {
  id?: string;
  name: string;
  site_url: string;
  folder_path: string;
  entity: string;
  interval_days: number;
  prune: boolean;
}

const EMPTY_FORM: FormState = {
  name: '',
  site_url: '',
  folder_path: '',
  entity: '',
  interval_days: 7,
  prune: true,
};

function fmtDate(iso: string | null): string {
  if (!iso) return 'jamais';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ScheduledSourcesPanel() {
  const { configs, isLoading, createConfig, updateConfig, deleteConfig, runConfig, toggleEnabled, isMutating } =
    useConnectorConfigs();
  const [form, setForm] = useState<FormState | null>(null);

  const openCreate = () => setForm({ ...EMPTY_FORM });
  const openEdit = (c: ConnectorConfigItem) =>
    setForm({
      id: c.id,
      name: c.name,
      site_url: c.site_url ?? '',
      folder_path: c.folder_path ?? '',
      entity: c.entity ?? '',
      interval_days: Math.max(1, Math.round(c.interval_seconds / DAY)),
      prune: c.prune,
    });

  const submit = async () => {
    if (!form || !form.name.trim() || !form.site_url.trim()) return;
    const payload: ConnectorConfigPayload = {
      name: form.name.trim(),
      connector_type: 'sharepoint',
      site_url: form.site_url.trim(),
      folder_path: form.folder_path.trim() || null,
      entity: form.entity.trim() || null,
      interval_seconds: Math.max(300, Math.round(form.interval_days * DAY)),
      prune: form.prune,
    };
    if (form.id) {
      updateConfig(form.id, payload);
    } else {
      await createConfig(payload);
    }
    setForm(null);
  };

  return (
    <div className="mt-8 rounded-xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Sources SharePoint planifiées</h3>
          <p className="text-xs text-muted-foreground">
            Re-synchronisées automatiquement (delta) selon leur cadence. Credentials lus côté serveur.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          <Plus className="h-4 w-4" /> Ajouter
        </button>
      </div>

      {form && (
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-dashed border-border bg-muted/20 p-4 sm:grid-cols-2">
          <input className="rounded-md border border-border bg-background px-3 py-1.5 text-sm" placeholder="Nom"
                 value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="rounded-md border border-border bg-background px-3 py-1.5 text-sm" placeholder="URL du site SharePoint"
                 value={form.site_url} onChange={(e) => setForm({ ...form, site_url: e.target.value })} />
          <input className="rounded-md border border-border bg-background px-3 py-1.5 text-sm" placeholder="Dossier (optionnel)"
                 value={form.folder_path} onChange={(e) => setForm({ ...form, folder_path: e.target.value })} />
          <input className="rounded-md border border-border bg-background px-3 py-1.5 text-sm" placeholder="Entité (optionnel)"
                 value={form.entity} onChange={(e) => setForm({ ...form, entity: e.target.value })} />
          <label className="flex items-center gap-2 text-sm text-foreground">
            Cadence (jours)
            <input type="number" min={1} className="w-20 rounded-md border border-border bg-background px-2 py-1 text-sm"
                   value={form.interval_days} onChange={(e) => setForm({ ...form, interval_days: Number(e.target.value) })} />
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" checked={form.prune} onChange={(e) => setForm({ ...form, prune: e.target.checked })} />
            Supprimer les docs absents de la source (prune)
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <button onClick={submit} disabled={isMutating || !form.name.trim() || !form.site_url.trim()}
                    className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
              {form.id ? 'Enregistrer' : 'Créer'}
            </button>
            <button onClick={() => setForm(null)}
                    className="rounded-lg border border-border px-3 py-1.5 text-sm text-foreground hover:bg-muted">
              Annuler
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : configs.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune source planifiée.</p>
      ) : (
        <div className="space-y-2">
          {configs.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-foreground">{c.name}</span>
                  {c.last_status === 'queued' && <span className="text-xs text-muted-foreground">(sync en cours…)</span>}
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {c.site_url}{c.folder_path ? ` → ${c.folder_path}` : ''} · tous les {Math.round(c.interval_seconds / DAY)} j · dernière : {fmtDate(c.last_sync_at)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-muted-foreground">
                  <input type="checkbox" checked={c.enabled} onChange={(e) => toggleEnabled(c.id, e.target.checked)} />
                  actif
                </label>
                <button title="Sync now" onClick={() => runConfig(c.id)} disabled={isMutating}
                        className="rounded-md border border-border p-1.5 hover:bg-muted disabled:opacity-50">
                  <RefreshCw className="h-4 w-4" />
                </button>
                <button title="Éditer" onClick={() => openEdit(c)}
                        className="rounded-md border border-border p-1.5 hover:bg-muted">
                  <Pencil className="h-4 w-4" />
                </button>
                <button title="Supprimer" onClick={() => deleteConfig(c.id)}
                        className="rounded-md border border-border p-1.5 text-destructive hover:bg-muted">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
