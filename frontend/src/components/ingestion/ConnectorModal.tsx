/**
 * ConnectorModal — formulaire de configuration et de lancement d'un crawl.
 * Trois variantes : local | web | sharepoint
 * Inspiré de l'UI Onyx pour SharePoint (sites, sous-dossiers, credentials Entra ID).
 */
import { useRef, useState } from 'react';
import { X, Play, Loader2, FolderOpen, Globe, Cloud } from 'lucide-react';
import type { ConnectorType, CrawlBody } from '@/hooks/use-connectors';
import type { CrawlLocalRequest, CrawlSharepointRequest, CrawlWebRequest } from '@/lib/api';
import { useEntities } from '@/hooks/use-entities';

// ── Helpers UI ────────────────────────────────────────────────────────────────

const PARSERS = ['docling', 'mineru', 'simple'] as const;
const STRATEGIES = ['by_token', 'by_sentence', 'by_block'] as const;

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

function TextInput({
  label,
  placeholder,
  value,
  onChange,
  required,
  type = 'text',
  hint,
}: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  type?: string;
  hint?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      <input
        type={type}
        required={required}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
      />
      {hint && <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded accent-primary"
      />
      <span className="text-sm text-card-foreground">{label}</span>
    </label>
  );
}

// ── Entity + validity_date fields (shared) ────────────────────────────────────

function EntityFields({
  entity,
  onEntityChange,
  validityDate,
  onValidityDateChange,
}: {
  entity: string;
  onEntityChange: (v: string) => void;
  validityDate: string;
  onValidityDateChange: (v: string) => void;
}) {
  const { entities } = useEntities();
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Entité (propriétaire)</label>
        <select
          value={entity}
          onChange={(e) => onEntityChange(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">— Aucune —</option>
          {entities.map((e) => (
            <option key={e.id} value={e.name}>{e.name}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Date d'expiration</label>
        <input
          type="date"
          value={validityDate}
          onChange={(e) => onValidityDateChange(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
    </div>
  );
}

// ── Formulaire Local ──────────────────────────────────────────────────────────

function LocalForm({ onSubmit, isLoading }: { onSubmit: (b: CrawlBody) => void; isLoading: boolean }) {
  const [directory, setDirectory] = useState('');
  const [ext, setExt] = useState('.pdf, .docx, .txt');
  const [recursive, setRecursive] = useState(true);
  const [parser, setParser] = useState<string>('docling');
  const [strategy, setStrategy] = useState<string>('by_token');
  const [entity, setEntity] = useState('');
  const [validityDate, setValidityDate] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const extList = ext
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => (s.startsWith('.') ? s : `.${s}`));
    const body: CrawlLocalRequest = {
      directory,
      ext: extList.length ? extList : ['.pdf'],
      recursive,
      parser,
      strategy,
      entity: entity || undefined,
      validity_date: validityDate || undefined,
    };
    onSubmit(body);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <TextInput
        label="Chemin du répertoire"
        placeholder="/data/documents ou C:\Documents"
        value={directory}
        onChange={setDirectory}
        required
        hint="Chemin absolu accessible par le worker Celery."
      />
      <TextInput
        label="Extensions (séparées par des virgules)"
        placeholder=".pdf, .docx, .txt"
        value={ext}
        onChange={setExt}
        hint="Seuls les fichiers avec ces extensions seront indexés."
      />
      <Checkbox label="Descendre dans les sous-répertoires" checked={recursive} onChange={setRecursive} />
      <div className="grid grid-cols-2 gap-3">
        <Select label="Parser" value={parser} onChange={setParser} options={PARSERS} />
        <Select label="Stratégie" value={strategy} onChange={setStrategy} options={STRATEGIES} />
      </div>
      <EntityFields
        entity={entity}
        onEntityChange={setEntity}
        validityDate={validityDate}
        onValidityDateChange={setValidityDate}
      />
      <SubmitButton isLoading={isLoading} />
    </form>
  );
}

// ── Formulaire Web ────────────────────────────────────────────────────────────

function WebForm({ onSubmit, isLoading }: { onSubmit: (b: CrawlBody) => void; isLoading: boolean }) {
  const [urlsText, setUrlsText] = useState('');
  const [mode, setMode] = useState<'pdf' | 'html'>('pdf');
  const [parser, setParser] = useState<string>('docling');
  const [strategy, setStrategy] = useState<string>('by_token');
  const [entity, setEntity] = useState('');
  const [validityDate, setValidityDate] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const urls = urlsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    if (!urls.length) return;
    const body: CrawlWebRequest = {
      urls,
      mode,
      parser,
      strategy,
      entity: entity || undefined,
      validity_date: validityDate || undefined,
    };
    onSubmit(body);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">
          URLs à crawler <span className="text-destructive">*</span>
        </label>
        <textarea
          required
          rows={4}
          placeholder={'https://docs.example.com/guide\nhttps://docs.example.com/api'}
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none font-mono"
        />
        <p className="mt-1 text-[11px] text-muted-foreground">Une URL par ligne. Playwright sera utilisé pour le rendu.</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Select label="Mode" value={mode} onChange={(v) => setMode(v as 'pdf' | 'html')} options={['pdf', 'html']} />
        <Select label="Parser" value={parser} onChange={setParser} options={PARSERS} />
        <Select label="Stratégie" value={strategy} onChange={setStrategy} options={STRATEGIES} />
      </div>
      <EntityFields
        entity={entity}
        onEntityChange={setEntity}
        validityDate={validityDate}
        onValidityDateChange={setValidityDate}
      />
      <SubmitButton isLoading={isLoading} />
    </form>
  );
}

// ── Formulaire SharePoint ─────────────────────────────────────────────────────

function SharePointForm({ onSubmit, isLoading }: { onSubmit: (b: CrawlBody) => void; isLoading: boolean }) {
  const [siteUrl, setSiteUrl] = useState('');
  const [siteName, setSiteName] = useState('');
  const [folderPath, setFolderPath] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [parser, setParser] = useState<string>('docling');
  const [strategy, setStrategy] = useState<string>('by_token');
  const [showCreds, setShowCreds] = useState(false);
  const [entity, setEntity] = useState('');
  const [validityDate, setValidityDate] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteUrl && !siteName) return;
    const body: CrawlSharepointRequest = {
      site_url: siteUrl || undefined,
      site_name: siteName || undefined,
      folder_path: folderPath || undefined,
      parser,
      strategy,
      client_id: clientId || undefined,
      client_secret: clientSecret || undefined,
      tenant_id: tenantId || undefined,
      entity: entity || undefined,
      validity_date: validityDate || undefined,
    };
    onSubmit(body);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Site */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 flex flex-col gap-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Site SharePoint</p>
        <TextInput
          label="URL complète du site"
          placeholder="https://contoso.sharepoint.com/sites/support"
          value={siteUrl}
          onChange={setSiteUrl}
          hint="Ex: https://contoso.sharepoint.com/sites/support/subfolder — seul ce dossier sera indexé."
        />
        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-border" />
          <span className="text-[11px] text-muted-foreground">ou</span>
          <div className="flex-1 h-px bg-border" />
        </div>
        <TextInput
          label="Nom court du site (alternatif à l'URL)"
          placeholder="support"
          value={siteName}
          onChange={setSiteName}
        />
        <TextInput
          label="Sous-dossier à indexer (optionnel)"
          placeholder="/Documents/Contrats"
          value={folderPath}
          onChange={setFolderPath}
          hint="Laisser vide pour indexer tout le site."
        />
      </div>

      {/* Parser / Strategy */}
      <div className="grid grid-cols-2 gap-3">
        <Select label="Parser" value={parser} onChange={setParser} options={PARSERS} />
        <Select label="Stratégie" value={strategy} onChange={setStrategy} options={STRATEGIES} />
      </div>

      {/* Credentials optionnels */}
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <button
          type="button"
          onClick={() => setShowCreds((v) => !v)}
          className="flex items-center gap-2 w-full text-left"
        >
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex-1">
            Credentials Entra ID (App Registration)
          </span>
          <span className="text-[11px] text-muted-foreground">{showCreds ? '▲ Masquer' : '▼ Afficher'}</span>
        </button>
        {!showCreds && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            Optionnel — si omis, les variables d'environnement{' '}
            <code className="font-mono">SHAREPOINT_CLIENT_ID / SECRET / TENANT_ID</code> seront utilisées.
          </p>
        )}
        {showCreds && (
          <div className="mt-3 flex flex-col gap-3">
            <TextInput
              label="Client ID (Application ID)"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={clientId}
              onChange={setClientId}
              hint="ID de l'App Registration dans Azure Entra ID."
            />
            <TextInput
              label="Client Secret"
              placeholder="••••••••••••••"
              value={clientSecret}
              onChange={setClientSecret}
              type="password"
            />
            <TextInput
              label="Tenant ID"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={tenantId}
              onChange={setTenantId}
            />
          </div>
        )}
      </div>

      <EntityFields
        entity={entity}
        onEntityChange={setEntity}
        validityDate={validityDate}
        onValidityDateChange={setValidityDate}
      />

      <SubmitButton isLoading={isLoading} />
    </form>
  );
}

// ── Submit button ─────────────────────────────────────────────────────────────

function SubmitButton({ isLoading }: { isLoading: boolean }) {
  return (
    <button
      type="submit"
      disabled={isLoading}
      className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-60 transition-opacity"
    >
      {isLoading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          Lancement en cours…
        </>
      ) : (
        <>
          <Play className="w-4 h-4" />
          Lancer le crawl
        </>
      )}
    </button>
  );
}

// ── Modal principal ───────────────────────────────────────────────────────────

const MODAL_META: Record<ConnectorType, { title: string; icon: React.FC<{ className?: string }> }> = {
  local: { title: 'Répertoire local', icon: FolderOpen },
  web: { title: 'Pages web', icon: Globe },
  sharepoint: { title: 'SharePoint / OneDrive', icon: Cloud },
};

interface ConnectorModalProps {
  type: ConnectorType;
  isLoading: boolean;
  onSubmit: (body: CrawlBody) => void;
  onClose: () => void;
}

export default function ConnectorModal({ type, isLoading, onSubmit, onClose }: ConnectorModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const meta = MODAL_META[type];
  const Icon = meta.icon;

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    >
      <div className="w-full max-w-lg bg-card rounded-2xl border border-border shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-border shrink-0">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="w-4 h-4 text-primary" />
          </div>
          <h2 className="text-base font-semibold text-card-foreground flex-1">
            Configurer — {meta.title}
          </h2>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        {/* Body scrollable */}
        <div className="overflow-y-auto p-6">
          {type === 'local' && <LocalForm onSubmit={onSubmit} isLoading={isLoading} />}
          {type === 'web' && <WebForm onSubmit={onSubmit} isLoading={isLoading} />}
          {type === 'sharepoint' && <SharePointForm onSubmit={onSubmit} isLoading={isLoading} />}
        </div>
      </div>
    </div>
  );
}
