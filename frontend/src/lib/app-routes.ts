import type { AppView } from '@/types/layout';

export const VIEW_PATHS: Record<AppView, string> = {
  chat: '/chat',
  ingestion: '/ingestion',
  admin: '/admin',
};

export function viewFromPath(pathname: string): AppView {
  if (pathname.startsWith('/chat')) return 'chat';
  if (pathname === VIEW_PATHS.ingestion) return 'ingestion';
  if (pathname === VIEW_PATHS.admin) return 'admin';
  return 'chat';
}

export function buildChatPath(sessionId?: string | null): string {
  return sessionId ? `${VIEW_PATHS.chat}/${sessionId}` : VIEW_PATHS.chat;
}

export function buildViewPath(view: AppView, sessionId?: string | null): string {
  return view === 'chat' ? buildChatPath(sessionId) : VIEW_PATHS[view];
}
