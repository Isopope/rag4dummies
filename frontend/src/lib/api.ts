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

export interface TokenUsageBucket {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  call_count: number;
}

export interface TokenUsageCall {
  kind: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  raw_usage: Record<string, unknown>;
}

export interface TokenUsageSummary {
  llm: TokenUsageBucket;
  embeddings: TokenUsageBucket;
  total: TokenUsageBucket;
  calls: TokenUsageCall[];
}

export interface QueryRequest {
  question: string;
  source_filter?: string;
  conversation_summary?: string;
  session_id?: string;
  model?: string;
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
  usage?: TokenUsageSummary;
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
  session_id?: string;
  usage?: TokenUsageSummary;
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
  usage?: TokenUsageSummary;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// ── Modèles LLM ───────────────────────────────────────────────────────────────

export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default: string;
}

export async function getModels(): Promise<ModelsResponse> {
  const res = await fetch(`${BASE}/models`);
  await assertOk(res);
  return res.json();
}

export interface UserInfo {
  id: string;
  email: string;
  role: string;
}

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

export async function getMe(token: string): Promise<UserInfo> {
  const res = await fetch(`${BASE}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await assertOk(res);
  return res.json();
}

export async function register(email: string, password: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  await assertOk(res);
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
  token?: string | null,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers: jsonHeaders(token),
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
  entity?: string,
  validityDate?: string,
): Promise<IngestJobResponse> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('parser', parser);
  fd.append('strategy', strategy);
  if (entity) fd.append('entity', entity);
  if (validityDate) fd.append('validity_date', validityDate);
  const res = await fetch(`${BASE}/ingest/pdf`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  await assertOk(res);
  return res.json();
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export async function getJobStatus(taskId: string, token: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE}/jobs/${taskId}`, { headers: jsonHeaders(token) });
  await assertOk(res);
  return res.json();
}

// ── Sources ───────────────────────────────────────────────────────────────────

export interface DocumentItem {
  id: string;
  filename: string;
  source_path: string;
  status: 'pending' | 'processing' | 'indexed' | 'error';
  chunk_count: number;
  parser: string | null;
  strategy: string | null;
  task_id: string | null;
  entity: string | null;
  validity_date: string | null;
  created_at: string;
  ingested_at: string | null;
  error_message: string | null;
}

export interface DocumentListStats {
  total_documents: number;
  indexed_documents: number;
  total_chunks: number;
}

export interface PaginatedDocumentsResponse {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
  stats: DocumentListStats;
}

export async function listDocuments(
  token: string,
  params: { status?: string; limit?: number; offset?: number } = {},
): Promise<PaginatedDocumentsResponse> {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  if (params.status) search.set('status', params.status);
  const res = await fetch(`${BASE}/documents?${search}`, { headers: jsonHeaders(token) });
  await assertOk(res);
  return res.json();
}

export async function deleteDocument(sourcePath: string, token: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${encodeURIComponent(sourcePath)}`, {
    method: 'DELETE',
    headers: jsonHeaders(token),
  });
  await assertOk(res);
}

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
  await assertOk(res);
}

// ── Sessions ────────────────────────────────────────────────────────────────────

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: ChunkModel[];
  follow_up_suggestions: string[];
  usage?: TokenUsageSummary;
  created_at: string;
}

export interface SessionItem {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message: string | null;
}

export interface SessionDetail {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
}

export async function listSessions(token: string, limit = 50): Promise<SessionItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${BASE}/sessions?${params}`, { headers: jsonHeaders(token) });
  await assertOk(res);
  return res.json();
}

export async function getSession(sessionId: string, token: string): Promise<SessionDetail> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { headers: jsonHeaders(token) });
  await assertOk(res);
  return res.json();
}

export async function deleteSession(sessionId: string, token: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: jsonHeaders(token),
  });
  await assertOk(res);
}

export async function renameSession(sessionId: string, title: string, token: string): Promise<SessionItem> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify({ title }),
  });
  await assertOk(res);
  return res.json();
}

// ── Connectors (crawl) ────────────────────────────────────────────────────────

export interface CrawlLocalRequest {
  directory: string;
  ext: string[];
  recursive: boolean;
  parser: string;
  strategy: string;
  entity?: string;
  validity_date?: string;
}

export interface CrawlWebRequest {
  urls: string[];
  output_dir?: string;
  mode: 'pdf' | 'html';
  parser: string;
  strategy: string;
  entity?: string;
  validity_date?: string;
}

export interface CrawlSharepointRequest {
  site_url?: string;
  site_name?: string;
  folder_path?: string;
  output_dir?: string;
  parser: string;
  strategy: string;
  client_id?: string;
  client_secret?: string;
  tenant_id?: string;
  entity?: string;
  validity_date?: string;
}

export interface CrawlJobResponse {
  crawl_task_id: string;
  status: string;
  connector: string;
  message: string;
}

export async function crawlLocal(body: CrawlLocalRequest, token: string): Promise<CrawlJobResponse> {
  const res = await fetch(`${BASE}/connectors/local`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function crawlWeb(body: CrawlWebRequest, token: string): Promise<CrawlJobResponse> {
  const res = await fetch(`${BASE}/connectors/web`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function crawlSharepoint(body: CrawlSharepointRequest, token: string): Promise<CrawlJobResponse> {
  const res = await fetch(`${BASE}/connectors/sharepoint`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

// ── Entities (admin) ──────────────────────────────────────────────────────────

export interface EntityItem {
  id: string;
  name: string;
  created_at: string;
}

export async function listEntities(): Promise<EntityItem[]> {
  const res = await fetch(`${BASE}/entities`);
  await assertOk(res);
  return res.json();
}

export async function createEntity(name: string, token: string): Promise<EntityItem> {
  const res = await fetch(`${BASE}/entities`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ name }),
  });
  await assertOk(res);
  return res.json();
}

export async function deleteEntity(id: string, token: string): Promise<void> {
  const res = await fetch(`${BASE}/entities/${id}`, {
    method: 'DELETE',
    headers: jsonHeaders(token),
  });
  await assertOk(res);
}
