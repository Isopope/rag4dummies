import { describe, expect, it } from 'vitest';
import { buildChatPath, buildViewPath, VIEW_PATHS, viewFromPath } from '@/lib/app-routes';
import {
  mapCeleryStateToConnectorStatus,
  mapJobToIngestStatus,
  resolveSessionSaveStatus,
} from '@/lib/workflow-state';

describe('app-routes helpers', () => {
  it('maps known paths to app views', () => {
    expect(viewFromPath('/chat')).toBe('chat');
    expect(viewFromPath('/chat/abc-123')).toBe('chat');
    expect(viewFromPath('/ingestion')).toBe('ingestion');
    expect(viewFromPath('/admin')).toBe('admin');
    expect(viewFromPath('/unknown')).toBe('chat');
  });

  it('builds chat and view paths consistently', () => {
    expect(buildChatPath()).toBe(VIEW_PATHS.chat);
    expect(buildChatPath('session-42')).toBe('/chat/session-42');
    expect(buildViewPath('chat', 'session-42')).toBe('/chat/session-42');
    expect(buildViewPath('ingestion', 'session-42')).toBe(VIEW_PATHS.ingestion);
    expect(buildViewPath('admin')).toBe(VIEW_PATHS.admin);
  });
});

describe('workflow-state helpers', () => {
  it('resolves session persistence status explicitly', () => {
    expect(resolveSessionSaveStatus(true, true)).toBe('saved');
    expect(resolveSessionSaveStatus(false, true)).toBe('save_failed');
    expect(resolveSessionSaveStatus(undefined, true)).toBe('idle');
    expect(resolveSessionSaveStatus(false, false)).toBe('not_applicable');
  });

  it('maps ingest jobs to canonical frontend states', () => {
    expect(mapJobToIngestStatus('pending')).toBe('queued');
    expect(mapJobToIngestStatus('pending', 'STARTED')).toBe('processing');
    expect(mapJobToIngestStatus('indexed')).toBe('indexed');
    expect(mapJobToIngestStatus('error')).toBe('error');
    expect(mapJobToIngestStatus('processing')).toBe('processing');
    expect(mapJobToIngestStatus('unknown', 'FAILURE')).toBe('error');
    expect(mapJobToIngestStatus('processing', undefined, 3)).toBe('degraded');
  });

  it('maps connector celery states to canonical connector states', () => {
    expect(mapCeleryStateToConnectorStatus()).toBe('queued');
    expect(mapCeleryStateToConnectorStatus('PENDING')).toBe('queued');
    expect(mapCeleryStateToConnectorStatus('STARTED')).toBe('syncing');
    expect(mapCeleryStateToConnectorStatus('SUCCESS')).toBe('connected');
    expect(mapCeleryStateToConnectorStatus('FAILURE')).toBe('error');
    expect(mapCeleryStateToConnectorStatus('STARTED', 3)).toBe('degraded');
  });
});
