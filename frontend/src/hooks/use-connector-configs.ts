/**
 * useConnectorConfigs — gère les sources de connecteurs synchronisées
 * périodiquement (SharePoint planifié) : liste, création, édition, suppression,
 * et déclenchement manuel « Sync now ».
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createConnectorConfig,
  deleteConnectorConfig,
  listConnectorConfigs,
  runConnectorConfig,
  updateConnectorConfig,
  type ConnectorConfigItem,
  type ConnectorConfigPayload,
} from '@/lib/api';
import { useAuth } from '@/context/AuthContext';

const KEY = ['connector-configs'];

export function useConnectorConfigs() {
  const queryClient = useQueryClient();
  const { token } = useAuth();

  const query = useQuery<ConnectorConfigItem[]>({
    queryKey: KEY,
    queryFn: () => listConnectorConfigs(token!),
    enabled: !!token,
    staleTime: 15_000,
    // Rafraîchit tant qu'une source est en cours de synchronisation.
    refetchInterval: (q) => {
      const data = q.state.data;
      const running = data?.some((c) => c.last_status === 'queued');
      return running ? 5000 : false;
    },
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: KEY });

  const createMutation = useMutation({
    mutationFn: (body: ConnectorConfigPayload) => createConnectorConfig(body, token!),
    onSuccess: async () => { await invalidate(); toast.success('Source planifiée créée.'); },
    onError: () => toast.error('Impossible de créer la source.'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ConnectorConfigPayload> }) =>
      updateConnectorConfig(id, body, token!),
    onSuccess: async () => { await invalidate(); },
    onError: () => toast.error('Impossible de modifier la source.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteConnectorConfig(id, token!),
    onSuccess: async () => { await invalidate(); toast.success('Source supprimée.'); },
    onError: () => toast.error('Impossible de supprimer la source.'),
  });

  const runMutation = useMutation({
    mutationFn: (id: string) => runConnectorConfig(id, token!),
    onSuccess: async () => { await invalidate(); toast.success('Synchronisation lancée.'); },
    onError: () => toast.error('Impossible de lancer la synchronisation.'),
  });

  return {
    configs: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    refresh: invalidate,
    createConfig: (body: ConnectorConfigPayload) => createMutation.mutateAsync(body),
    updateConfig: (id: string, body: Partial<ConnectorConfigPayload>) => updateMutation.mutate({ id, body }),
    toggleEnabled: (id: string, enabled: boolean) => updateMutation.mutate({ id, body: { enabled } }),
    deleteConfig: (id: string) => deleteMutation.mutate(id),
    runConfig: (id: string) => runMutation.mutate(id),
    isMutating: createMutation.isPending || updateMutation.isPending || runMutation.isPending,
  };
}
