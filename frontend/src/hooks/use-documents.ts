import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listDocuments, deleteDocument } from '@/lib/api';
import type { DocumentItem } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

const DOCS_KEY = ['documents'];

export function useDocuments() {
  const queryClient = useQueryClient();
  const { token } = useAuth();

  const query = useQuery<DocumentItem[]>({
    queryKey: DOCS_KEY,
    queryFn: () => listDocuments(token!),
    enabled: !!token,
    staleTime: 15_000,
    refetchInterval: (q) => {
      // Polling actif si des documents sont en cours de traitement
      const data = q.state.data;
      const hasPending = data?.some((d) => d.status === 'pending' || d.status === 'processing');
      return hasPending ? 5000 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (sourcePath: string) => deleteDocument(sourcePath, token!),
    onSuccess: (_data, sourcePath) => {
      queryClient.setQueryData<DocumentItem[]>(DOCS_KEY, (prev) =>
        prev ? prev.filter((d) => d.source_path !== sourcePath) : [],
      );
      toast.success('Document supprimé.');
    },
    onError: () => toast.error('Impossible de supprimer le document.'),
  });

  return {
    documents: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    refresh: () => queryClient.invalidateQueries({ queryKey: DOCS_KEY }),
    deleteDocument: (sourcePath: string) => deleteMutation.mutate(sourcePath),
  };
}
