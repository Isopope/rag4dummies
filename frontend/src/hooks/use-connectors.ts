/**
 * useConnectors — gère l'état (persisté en localStorage) et le polling
 * des 3 connecteurs de crawl : local, web, sharepoint.
 *
 * Chaque connecteur mémorise son dernier crawl_task_id.
 * Le statut est mis à jour via polling de GET /jobs/{taskId} jusqu'à
 * succès ou échec.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  crawlLocal,
  crawlSharepoint,
  crawlWeb,
  getJobStatus,
  type CrawlLocalRequest,
  type CrawlSharepointRequest,
  type CrawlWebRequest,
} from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import {
  buildPollingDelayMessage,
  mapCeleryStateToConnectorStatus,
  type FrontendConnectorStatus,
} from '@/lib/workflow-state';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ConnectorType = 'local' | 'web' | 'sharepoint';
export type ConnectorStatus = FrontendConnectorStatus;

export type CrawlBody = CrawlLocalRequest | CrawlWebRequest | CrawlSharepointRequest;

export interface ConnectorCardState {
  type: ConnectorType;
  name: string;
  icon: string;
  description: string;
  status: ConnectorStatus;
  lastMessage: string | null;
  lastLaunchedAt: string | null;
  lastTaskId: string | null;
  isLaunching: boolean;
}

interface PersistedJob {
  taskId: string;
  launchedAt: string;
  message: string;
  /** Dernier état Celery connu — pour éviter de re-poll un job terminé. */
  celeryState?: string;
  consecutiveFailures?: number;
}

const LS_KEY = (type: ConnectorType) => `rag_crawl_${type}`;

const CONNECTOR_META: Record<ConnectorType, { name: string; icon: string; description: string }> = {
  local: {
    name: 'Répertoire local',
    icon: 'HardDrive',
    description: 'Scanner un dossier local ou un montage réseau (NFS/CIFS)',
  },
  web: {
    name: 'Pages web',
    icon: 'Globe',
    description: 'Crawler des pages web via Playwright (rendu complet)',
  },
  sharepoint: {
    name: 'SharePoint / OneDrive',
    icon: 'CloudIcon',
    description: 'Synchroniser un site SharePoint via Microsoft Graph API',
  },
};

const TERMINAL_STATES = new Set(['SUCCESS', 'FAILURE', 'REVOKED']);

function loadJob(type: ConnectorType): PersistedJob | null {
  try {
    const raw = localStorage.getItem(LS_KEY(type));
    return raw ? (JSON.parse(raw) as PersistedJob) : null;
  } catch {
    return null;
  }
}

function saveJob(type: ConnectorType, job: PersistedJob) {
  localStorage.setItem(LS_KEY(type), JSON.stringify(job));
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useConnectors() {
  const { token } = useAuth();

  const TYPES: ConnectorType[] = ['local', 'web', 'sharepoint'];

  // État des jobs persistés, initialisé depuis localStorage
  const [jobs, setJobs] = useState<Record<ConnectorType, PersistedJob | null>>(() => ({
    local: loadJob('local'),
    web: loadJob('web'),
    sharepoint: loadJob('sharepoint'),
  }));

  const [launching, setLaunching] = useState<Record<ConnectorType, boolean>>({
    local: false,
    web: false,
    sharepoint: false,
  });

  // Polling interval ref par connecteur
  const intervals = useRef<Partial<Record<ConnectorType, ReturnType<typeof setInterval>>>>({});

  // ── Polling ────────────────────────────────────────────────────────────────
  const startPolling = useCallback(
    (type: ConnectorType, taskId: string) => {
      if (intervals.current[type]) return; // déjà en cours

      intervals.current[type] = setInterval(async () => {
        if (!token) return;
        try {
          const job = await getJobStatus(taskId, token);
          const celeryState = job.celery_state;

          setJobs((prev) => {
            const existing = prev[type];
            if (!existing) return prev;
            const updated: PersistedJob = {
              ...existing,
              celeryState,
              consecutiveFailures: 0,
              message: job.error ?? existing.message,
            };
            saveJob(type, updated);
            return { ...prev, [type]: updated };
          });

          if (TERMINAL_STATES.has(celeryState)) {
            clearInterval(intervals.current[type]);
            delete intervals.current[type];
          }
        } catch {
          setJobs((prev) => {
            const existing = prev[type];
            if (!existing) return prev;
            const consecutiveFailures = (existing.consecutiveFailures ?? 0) + 1;
            const updated: PersistedJob = {
              ...existing,
              consecutiveFailures,
              message: buildPollingDelayMessage(`du connecteur ${CONNECTOR_META[type].name.toLowerCase()}`),
            };
            saveJob(type, updated);
            return { ...prev, [type]: updated };
          });
        }
      }, 5000);
    },
    [token],
  );

  // Démarrer le polling pour les jobs non-terminaux au montage
  useEffect(() => {
    if (!token) return;
    for (const type of TYPES) {
      const job = jobs[type];
      if (job && job.taskId && !TERMINAL_STATES.has(job.celeryState ?? '')) {
        startPolling(type, job.taskId);
      }
    }
    return () => {
      for (const t of TYPES) {
        if (intervals.current[t]) {
          clearInterval(intervals.current[t]);
          delete intervals.current[t];
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Launch ─────────────────────────────────────────────────────────────────
  const launch = useCallback(
    async (type: ConnectorType, body: CrawlBody) => {
      if (!token) return;
      setLaunching((prev) => ({ ...prev, [type]: true }));
      try {
        let resp;
        if (type === 'local') resp = await crawlLocal(body as CrawlLocalRequest, token);
        else if (type === 'web') resp = await crawlWeb(body as CrawlWebRequest, token);
        else resp = await crawlSharepoint(body as CrawlSharepointRequest, token);

        const persisted: PersistedJob = {
          taskId: resp.crawl_task_id,
          launchedAt: new Date().toISOString(),
          message: resp.message,
          celeryState: 'PENDING',
          consecutiveFailures: 0,
        };
        saveJob(type, persisted);
        setJobs((prev) => ({ ...prev, [type]: persisted }));

        // Annuler l'éventuel polling précédent et en démarrer un nouveau
        if (intervals.current[type]) {
          clearInterval(intervals.current[type]);
          delete intervals.current[type];
        }
        startPolling(type, resp.crawl_task_id);
      } finally {
        setLaunching((prev) => ({ ...prev, [type]: false }));
      }
    },
    [token, startPolling],
  );

  // ── Construire les ConnectorCardState ──────────────────────────────────────
  const connectors: ConnectorCardState[] = TYPES.map((type) => {
    const job = jobs[type];
    const meta = CONNECTOR_META[type];

    let status: ConnectorStatus = 'idle';
    if (job) {
      status = mapCeleryStateToConnectorStatus(job.celeryState, job.consecutiveFailures ?? 0);
    }

    return {
      type,
      ...meta,
      status,
      lastMessage: job?.message ?? null,
      lastLaunchedAt: job?.launchedAt ?? null,
      lastTaskId: job?.taskId ?? null,
      isLaunching: launching[type],
    };
  });

  return { connectors, launch };
}
