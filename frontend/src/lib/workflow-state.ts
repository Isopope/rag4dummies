export type ChatRunStatus =
  | 'idle'
  | 'starting'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'degraded';

export type SessionSaveStatus = 'idle' | 'saved' | 'not_applicable' | 'save_failed';

export interface ChatRunState {
  status: ChatRunStatus;
  sessionSaveStatus: SessionSaveStatus;
  warnings: string[];
  activeAssistantId?: string;
  error?: string;
}

export const IDLE_CHAT_RUN_STATE: ChatRunState = {
  status: 'idle',
  sessionSaveStatus: 'idle',
  warnings: [],
};

export type FrontendIngestStatus =
  | 'uploading'
  | 'queued'
  | 'processing'
  | 'indexed'
  | 'error'
  | 'degraded';

export type FrontendConnectorStatus =
  | 'idle'
  | 'queued'
  | 'syncing'
  | 'connected'
  | 'error'
  | 'degraded';

export const POLLING_DEGRADED_THRESHOLD = 3;

export function isPollingDegraded(consecutiveFailures: number): boolean {
  return consecutiveFailures >= POLLING_DEGRADED_THRESHOLD;
}

export function buildPollingDelayMessage(subject: string): string {
  return `Le suivi ${subject} est temporairement indisponible. Nouvel essai automatique en cours.`;
}

export function resolveSessionSaveStatus(
  sessionSaved: boolean | null | undefined,
  isAuthenticated: boolean,
): SessionSaveStatus {
  if (!isAuthenticated) return 'not_applicable';
  if (sessionSaved === true) return 'saved';
  if (sessionSaved === false) return 'save_failed';
  return 'idle';
}

export function mapJobToIngestStatus(
  status: string,
  celeryState?: string,
  consecutiveFailures = 0,
): FrontendIngestStatus {
  if (isPollingDegraded(consecutiveFailures)) {
    return 'degraded';
  }

  switch (status) {
    case 'indexed':
      return 'indexed';
    case 'error':
      return 'error';
    case 'processing':
      return 'processing';
    case 'pending':
      return celeryState === 'STARTED' || celeryState === 'RETRY' ? 'processing' : 'queued';
    case 'unknown':
      if (celeryState === 'FAILURE' || celeryState === 'REVOKED') return 'error';
      if (celeryState === 'STARTED' || celeryState === 'RETRY' || celeryState === 'SUCCESS') {
        return 'processing';
      }
      return 'queued';
    default:
      return 'processing';
  }
}

export function mapCeleryStateToConnectorStatus(
  celeryState?: string,
  consecutiveFailures = 0,
): FrontendConnectorStatus {
  if (isPollingDegraded(consecutiveFailures)) {
    return 'degraded';
  }

  if (!celeryState) {
    return 'queued';
  }

  switch (celeryState) {
    case 'SUCCESS':
      return 'connected';
    case 'FAILURE':
    case 'REVOKED':
      return 'error';
    case 'STARTED':
    case 'RETRY':
      return 'syncing';
    case 'PENDING':
      return 'queued';
    default:
      return 'idle';
  }
}
