import { useState, useEffect, useCallback } from 'react';
import { listEntities, createEntity, deleteEntity } from '@/lib/api';
import type { EntityItem } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

export function useEntities() {
  const { token } = useAuth();
  const [entities, setEntities] = useState<EntityItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listEntities();
      setEntities(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erreur chargement entités';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = useCallback(
    async (name: string) => {
      if (!token) return;
      try {
        const entity = await createEntity(name, token);
        setEntities((prev) => [...prev, entity]);
        toast.success(`Entité « ${entity.name} » créée.`);
        return entity;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Erreur création entité';
        toast.error(msg);
      }
    },
    [token],
  );

  const remove = useCallback(
    async (id: string, name: string) => {
      if (!token) return;
      try {
        await deleteEntity(id, token);
        setEntities((prev) => prev.filter((e) => e.id !== id));
        toast.success(`Entité « ${name} » supprimée.`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Erreur suppression entité';
        toast.error(msg);
      }
    },
    [token],
  );

  return { entities, isLoading, create, remove, reload: load };
}
