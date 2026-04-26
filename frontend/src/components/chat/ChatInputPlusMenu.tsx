import { Plus, Image as ImageIcon, Database, PencilRuler, Sparkles } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface ChatInputPlusMenuProps {
  onAddImage: () => void;
  onAddStory?: () => void;
  onOpenSkills?: () => void;
  onOpenDatabase?: () => void;
  hasSkills?: boolean;
  hasDatabases?: boolean;
}

export function ChatInputPlusMenu({
  onAddImage,
  onAddStory,
  onOpenSkills,
  onOpenDatabase,
  hasSkills = true,
  hasDatabases = true,
}: ChatInputPlusMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Add attachment"
          className="shrink-0 p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuItem onSelect={onAddImage} className="gap-2">
          <ImageIcon className="size-4" />
          Téléverser une image
        </DropdownMenuItem>
        {hasDatabases && onOpenDatabase && (
          <DropdownMenuItem onSelect={onOpenDatabase} className="gap-2">
            <Database className="size-4" />
            Tables de la base
          </DropdownMenuItem>
        )}
        {onAddStory && (
          <DropdownMenuItem onSelect={onAddStory} className="gap-2">
            <Sparkles className="size-4" />
            Mode story
          </DropdownMenuItem>
        )}
        {hasSkills && onOpenSkills && (
          <DropdownMenuItem onSelect={onOpenSkills} className="gap-2">
            <PencilRuler className="size-4" />
            Skills
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
