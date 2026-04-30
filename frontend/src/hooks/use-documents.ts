import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listDocuments, deleteDocument } from '@/lib/api';
import type { DocumentItem, DocumentListStats, PaginatedDocumentsResponse } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

const DOCS_KEY = ['documents'];
const DEFAULT_PAGE_SIZE = 10;
const EMPTY_STATS: DocumentListStats = {
  total_documents: 0,
  indexed_documents: 0,
  total_chunks: 0,
};

export function useDocuments() {
  const queryClient = useQueryClient();
  const { token } = useAuth();
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const query = useQuery<PaginatedDocumentsResponse>({
    queryKey: [...DOCS_KEY, pageIndex, pageSize],
    queryFn: () =>
      listDocuments(token!, {
        limit: pageSize,
        offset: pageIndex * pageSize,
      }),
    enabled: !!token,
    staleTime: 15_000,
    placeholderData: (previousData) => previousData,
    refetchInterval: (q) => {
      const data = q.state.data;
      const hasPending = data?.items.some((d) => d.status === 'pending' || d.status === 'processing');
      return hasPending ? 5000 : false;
    },
  });

  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (pageIndex === 0) return;
    if (!query.data) return;
    if (query.data.items.length > 0) return;
    setPageIndex(Math.max(0, pageCount - 1));
  }, [pageCount, pageIndex, query.data]);

  const deleteMutation = useMutation({
    mutationFn: (sourcePath: string) => deleteDocument(sourcePath, token!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: DOCS_KEY });
      toast.success('Document supprimé.');
    },
    onError: () => toast.error('Impossible de supprimer le document.'),
  });

  return {
    documents: query.data?.items ?? [],
    stats: query.data?.stats ?? EMPTY_STATS,
    total,
    pageIndex,
    pageSize,
    pageCount,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    setPageIndex,
    setPageSize: (size: number) => {
      setPageSize(size);
      setPageIndex(0);
    },
    refresh: () => queryClient.invalidateQueries({ queryKey: DOCS_KEY }),
    deleteDocument: (sourcePath: string) => deleteMutation.mutate(sourcePath),
  };
}
