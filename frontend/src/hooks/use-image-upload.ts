import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';

export interface UploadedImage {
  id: string;
  file: File;
  url: string;
  name: string;
}

const MAX_FILES = 10;
const MAX_SIZE_MB = 20;

export function useImageUpload() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((files: FileList | File[]) => {
    const fileArray = Array.from(files).filter((f) => f.type.startsWith('image/'));
    if (fileArray.length === 0) return;

    setImages((prev) => {
      const remaining = MAX_FILES - prev.length;
      if (remaining <= 0) {
        toast.error(`Maximum ${MAX_FILES} images par message.`);
        return prev;
      }
      const accepted: UploadedImage[] = [];
      for (const file of fileArray.slice(0, remaining)) {
        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
          toast.error(`${file.name} dépasse ${MAX_SIZE_MB}MB.`);
          continue;
        }
        accepted.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
          file,
          url: URL.createObjectURL(file),
          name: file.name,
        });
      }
      return [...prev, ...accepted];
    });
  }, []);

  const removeImage = useCallback((id: string) => {
    setImages((prev) => {
      const target = prev.find((i) => i.id === id);
      if (target) URL.revokeObjectURL(target.url);
      return prev.filter((i) => i.id !== id);
    });
  }, []);

  const clearImages = useCallback(() => {
    setImages((prev) => {
      prev.forEach((i) => URL.revokeObjectURL(i.url));
      return [];
    });
  }, []);

  const handlePaste = useCallback(
    (e: ClipboardEvent | React.ClipboardEvent) => {
      const items = (e as ClipboardEvent).clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === 'file') {
          const f = item.getAsFile();
          if (f && f.type.startsWith('image/')) files.push(f);
        }
      }
      if (files.length) addFiles(files);
    },
    [addFiles],
  );

  const openPicker = useCallback(() => inputRef.current?.click(), []);

  return {
    images,
    hasImages: images.length > 0,
    addFiles,
    removeImage,
    clearImages,
    handlePaste,
    openPicker,
    inputRef,
  };
}
