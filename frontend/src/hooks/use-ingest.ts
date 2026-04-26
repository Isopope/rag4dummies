import { useState, useCallback, useRef, useEffect } from 'react';
import { uploadPDF, getJobStatus } from '@/lib/api';
import type { JobStatusResponse } from '@/lib/api';
import type { UploadedFile } from '@/types/chat';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

interface PendingJob {
  taskId: string;
  fileId: string;
}

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
          if (status.status === 'indexed') {
            updateFile(job.fileId, { status: 'indexed', progress: 100 });
            pendingRef.current = pendingRef.current.filter((j) => j.fileId !== job.fileId);
          } else if (status.status === 'error') {
            updateFile(job.fileId, { status: 'error', progress: undefined });
            pendingRef.current = pendingRef.current.filter((j) => j.fileId !== job.fileId);
            toast.error(`Indexation échouée : ${status.filename ?? job.taskId}`);
          } else {
            updateFile(job.fileId, { status: 'processing', progress: 50 });
          }
        } catch {
          // Network error — retry next tick
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
    async (file: File, parser = 'mineru', strategy = 'by_sentence') => {
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
        const resp = await uploadPDF(file, parser, strategy, token);
        updateFile(id, { status: 'processing', progress: 30 });
        pendingRef.current.push({ taskId: resp.task_id, fileId: id });
        toast.success(`"${file.name}" soumis à l'indexation.`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Erreur upload';
        updateFile(id, { status: 'error', progress: undefined });
        toast.error(`Upload échoué : ${msg}`);
      }
    },
    [token, updateFile],
  );

  return { files, upload };
}
