import { useState, useCallback, useRef, useEffect } from 'react';
import { uploadDocument, getJobStatus } from '@/lib/api';
import type { JobStatusResponse } from '@/lib/api';
import type { UploadedFile } from '@/types/chat';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import {
  buildPollingDelayMessage,
  isPollingDegraded,
  mapJobToIngestStatus,
} from '@/lib/workflow-state';

interface PendingJob {
  taskId: string;
  fileId: string;
  consecutiveFailures: number;
}

const DEFAULT_PARSER = 'mineru';
const DEFAULT_STRATEGY = 'by_sentence';

export function useIngest() {
  const { token } = useAuth();
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const pendingRef = useRef<PendingJob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const updateFile = useCallback((id: string, patch: Partial<UploadedFile>) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  }, []);

  // Polling loop for in-progress ingest jobs
  useEffect(() => {
    timerRef.current = setInterval(async () => {
      const jobs = [...pendingRef.current];
      if (!jobs.length) return;
      for (const job of jobs) {
        try {
          const status: JobStatusResponse = await getJobStatus(job.taskId, token!);
          const mappedStatus = mapJobToIngestStatus(status.status, status.celery_state);
          pendingRef.current = pendingRef.current.map((pending) =>
            pending.fileId === job.fileId ? { ...pending, consecutiveFailures: 0 } : pending,
          );

          if (mappedStatus === 'indexed') {
            updateFile(job.fileId, { status: 'indexed', progress: 100, statusMessage: undefined });
            pendingRef.current = pendingRef.current.filter((j) => j.fileId !== job.fileId);
          } else if (mappedStatus === 'error') {
            updateFile(job.fileId, {
              status: 'error',
              progress: undefined,
              statusMessage: status.error ?? undefined,
            });
            pendingRef.current = pendingRef.current.filter((j) => j.fileId !== job.fileId);
            toast.error(`Indexation échouée : ${status.error ?? status.filename ?? job.taskId}`);
          } else {
            updateFile(job.fileId, {
              status: mappedStatus,
              progress: mappedStatus === 'queued' ? 20 : 50,
              statusMessage: undefined,
            });
          }
        } catch {
          const nextFailures = job.consecutiveFailures + 1;
          pendingRef.current = pendingRef.current.map((pending) =>
            pending.fileId === job.fileId ? { ...pending, consecutiveFailures: nextFailures } : pending,
          );

          if (isPollingDegraded(nextFailures)) {
            updateFile(job.fileId, {
              status: 'degraded',
              progress: undefined,
              statusMessage: buildPollingDelayMessage("de l'indexation"),
            });
          }
        }
      }
    }, 3000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [updateFile]);

  const upload = useCallback(
    async (file: File, entity?: string, validityDate?: string) => {
      if (!token) {
        toast.error('Connectez-vous pour uploader des fichiers.', {
          action: { label: 'Se connecter', onClick: () => (window.location.href = '/login') },
        });
        return;
      }

      const id = `f-${Date.now()}`;
      setFiles((prev) => [
        {
          id,
          name: file.name,
          size: `${(file.size / 1024).toFixed(0)} Ko`,
          type: file.type,
          status: 'uploading',
          progress: 10,
        },
        ...prev,
      ]);

      try {
        const resp = await uploadDocument(file, DEFAULT_PARSER, DEFAULT_STRATEGY, token, entity, validityDate);
        updateFile(id, { status: 'queued', progress: 20, statusMessage: undefined });
        pendingRef.current.push({ taskId: resp.task_id, fileId: id, consecutiveFailures: 0 });
        toast.success(`"${file.name}" soumis à l'indexation.`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Erreur upload';
        updateFile(id, { status: 'error', progress: undefined, statusMessage: msg });
        toast.error(`Upload échoué : ${msg}`);
      }
    },
    [token, updateFile],
  );

  return { files, upload };
}
