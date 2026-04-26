import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listSessions, deleteSession, renameSession, getSession } from '@/lib/api';
import type { SessionItem, SessionDetail } from '@/lib/api';
import { toast } from 'sonner';

const SESSIONS_KEY = ['sessions'];

export function useSessions(userId = 'anonymous') {
  const queryClient = useQueryClient();

  const query = useQuery<SessionItem[]>({
    queryKey: SESSIONS_KEY,
    queryFn: () => listSessions(userId),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: (_data, sessionId) => {
      queryClient.setQueryData<SessionItem[]>(SESSIONS_KEY, (prev) =>
        prev ? prev.filter((s) => s.id !== sessionId) : [],
      );
      toast.success('Session supprimée.');
    },
    onError: () => toast.error('Impossible de supprimer la session.'),
  });

  const renameMutation = useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) =>
      renameSession(sessionId, title),
    onSuccess: (updated) => {
      queryClient.setQueryData<SessionItem[]>(SESSIONS_KEY, (prev) =>
        prev ? prev.map((s) => (s.id === updated.id ? updated : s)) : [],
      );
    },
    onError: () => toast.error('Impossible de renommer la session.'),
  });

  /** Invalide le cache pour forcer un rechargement de la liste */
  const refresh = () => queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });

  /** Ajoute ou met à jour une session dans le cache local (optimistic) */
  const upsertLocal = (session: SessionItem) => {
    queryClient.setQueryData<SessionItem[]>(SESSIONS_KEY, (prev) => {
      if (!prev) return [session];
      const exists = prev.some((s) => s.id === session.id);
      return exists
        ? prev.map((s) => (s.id === session.id ? session : s))
        : [session, ...prev];
    });
  };

  return {
    sessions:   query.data ?? [],
    isLoading:  query.isLoading,
    error:      query.error,
    refresh,
    upsertLocal,
    deleteSession: (sessionId: string) => deleteMutation.mutate(sessionId),
    renameSession: (sessionId: string, title: string) =>
      renameMutation.mutate({ sessionId, title }),
  };
}

export function useSessionDetail(sessionId: string | null) {
  return useQuery<SessionDetail>({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: !!sessionId,
    staleTime: 60_000,
  });
}
