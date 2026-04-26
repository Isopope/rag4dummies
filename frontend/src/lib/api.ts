/**
 * Client HTTP pour l'API FastAPI RAG.
 * BASE = /api — proxied par Vite vers http://localhost:8000
 */

const BASE = '/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function jsonHeaders(token?: string | null): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

async function assertOk(res: Response): Promise<void> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
}

// ── Types (miroir des modèles Pydantic) ───────────────────────────────────────

export interface BboxModel {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ChunkModel {
  source: string;
  page_content: string;
  page_idx: number;
  kind: string;
  title_path: string;
  chunk_index: number;
  rerank_score?: number;
  score?: number;
  bboxes: BboxModel[];
  pdf_url?: string;
}

export interface QueryRequest {
  question: string;
  source_filter?: string;
  conversation_summary?: string;
}

export interface QueryResponse {
  question_id: string;
  question: string;
  answer: string;
  sources: ChunkModel[];
  follow_up_suggestions: string[];
  conversation_title?: string;
  n_retrieved: number;
  decision_log: Record<string, unknown>[];
  error?: string;
}

export interface StreamEvent {
  type: 'node_update' | 'answer' | 'done' | 'error';
  node?: string;
  message?: string;
  answer?: string;
  sources?: ChunkModel[];
  follow_up_suggestions?: string[];
  conversation_title?: string;
  question_id?: string;
  error?: string;
}

export interface IngestJobResponse {
  task_id: string;
  status: string;
  source: string;
  filename: string;
  pdf_url?: string;
  chunk_count: number;
  error?: string;
}

export interface JobStatusResponse {
  task_id: string;
  celery_state: string;
  status: string;
  source?: string;
  filename?: string;
  chunk_count: number;
  pdf_url?: string;
  error?: string;
}

export interface SourceItem {
  source: string;
  name: string;
  n_chunks: number;
}

export interface SourcesResponse {
  sources: SourceItem[];
  total_chunks: number;
}

export interface FeedbackPayload {
  question: string;
  answer: string;
  rating: number;
  comment?: string;
  user_id?: string;
  question_id?: string;
  conversation_title?: string;
  sources?: ChunkModel[];
  follow_up_suggestions?: string[];
  n_retrieved?: number;
  decision_log?: Record<string, unknown>[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<LoginResponse> {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE}/auth/jwt/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  });
  await assertOk(res);
  return res.json();
}

// ── Query (sync) ──────────────────────────────────────────────────────────────

export async function queryRAG(request: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${BASE}/query`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(request),
  });
  await assertOk(res);
  return res.json();
}

// ── Query (streaming SSE) ─────────────────────────────────────────────────────

export async function* streamQueryRAG(
  request: QueryRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(request),
    signal,
  });
  await assertOk(res);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const json = line.slice(6).trim();
          if (json && json !== '[DONE]') {
            try {
              yield JSON.parse(json) as StreamEvent;
            } catch {
              // skip malformed event
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Ingest ────────────────────────────────────────────────────────────────────

export async function uploadPDF(
  file: File,
  parser: string,
  strategy: string,
  token: string,
): Promise<IngestJobResponse> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('parser', parser);
  fd.append('strategy', strategy);
  const res = await fetch(`${BASE}/ingest/pdf`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  await assertOk(res);
  return res.json();
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export async function getJobStatus(taskId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE}/jobs/${taskId}`, { headers: jsonHeaders() });
  await assertOk(res);
  return res.json();
}

// ── Sources ───────────────────────────────────────────────────────────────────

export async function listSources(): Promise<SourcesResponse> {
  const res = await fetch(`${BASE}/sources`, { headers: jsonHeaders() });
  await assertOk(res);
  return res.json();
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export async function submitFeedback(data: FeedbackPayload): Promise<void> {
  const res = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  