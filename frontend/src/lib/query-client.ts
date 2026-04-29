import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient();

export function clearPrivateQueryData() {
  queryClient.removeQueries({ queryKey: ['sessions'] });
  queryClient.removeQueries({ queryKey: ['session'] });
  queryClient.removeQueries({ queryKey: ['documents'] });
}
