import type { CellValue } from '@/lib/table-utils';

export type MessageContentType = 'text' | 'image' | 'chart' | 'json' | 'code' | 'file' | 'table';

export interface ChartData {
  type: 'bar' | 'line' | 'pie' | 'area' | 'kpi_card';
  title?: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  colors?: string[];
  /** When 'date', enables the date range selector. */
  xKeyType?: 'date' | 'category' | 'number';
  /** KPI card only */
  kpi?: {
    valueKey: string;
    label?: string;
    /** numeric variation (e.g. 0.23 for +23%) */
    variation?: number;
    unit?: string;
  };
}

export interface TableData {
  title?: string;
  columns?: string[];
  rows: Record<string, CellValue>[];
}

export interface MessageContent {
  type: MessageContentType;
  text?: string;
  imageUrl?: string;
  chartData?: ChartData;
  tableData?: TableData;
  jsonData?: unknown;
  code?: string;
  language?: string;
  fileName?: string;
  fileSize?: string;
}

export interface MessageFeedback {
  vote: 'up' | 'down';
  explanation?: string;
}

export interface MessageSource {
  id: string;
  title: string;
  excerpt?: string;
  url?: string;
}

export interface AttachedImage {
  id: string;
  url: string;
  name: string;
}

export interface AgentStep {
  node: string;
  message: string;
  timestamp: Date;
  status: 'running' | 'done';
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  contents: MessageContent[];
  timestamp: Date;
  isStreaming?: boolean;
  feedback?: MessageFeedback;
  sources?: MessageSource[];
  followUpSuggestions?: string[];
  attachedImages?: AttachedImage[];
  /** Agent processing steps (populated from SSE node_update events) */
  steps?: AgentStep[];
}

export interface ChatSession {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: Date;
  messageCount: number;
}

export type ConnectorStatus = 'connected' | 'syncing' | 'error' | 'disconnected';

export interface Connector {
  id: string;
  name: string;
  type: string;
  icon: string;
  status: ConnectorStatus;
  documentsCount: number;
  lastSync?: Date;
  description: string;
}

export interface UploadedFile {
  id: string;
  name: string;
  size: string;
  type: string;
  status: 'uploading' | 'processing' | 'indexed' | 'error';
  progress?: number;
  uploadedAt: Date;
}
