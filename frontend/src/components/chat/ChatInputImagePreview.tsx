import { X } from 'lucide-react';
import type { UploadedImage } from '@/hooks/use-image-upload';

interface ChatInputImagePreviewProps {
  images: UploadedImage[];
  onRemove: (id: string) => void;
}

export function ChatInputImagePreview({ images, onRemove }: ChatInputImagePreviewProps) {
  if (images.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-3 pt-3">
      {images.map((image) => (
        <div key={image.id} className="relative group/preview">
          <img
            src={image.url}
            alt={image.name}
            className="h-16 w-16 rounded-md object-cover border border-border"
          />
          <button
            type="button"
            onClick={() => onRemove(image.id)}
            aria-label={`Remove ${image.name}`}
            className="absolute -top-1.5 -right-1.5 size-5 rounded-full bg-foreground text-background flex items-center justify-center opacity-0 group-hover/preview:opacity-100 transition-opacity cursor-pointer"
          >
            <X className="size-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
