import { useQuery } from '@tanstack/react-query';
import { listSources } from '@/lib/api';

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: listSources,
    staleTime: 30_000,
    retry: 2,
  });
}
