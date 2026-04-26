import { MessageSquare } from 'lucide-react';

const SAVED_PROMPTS = [
  { id: '1', text: 'Résume ce document en 3 points clés' },
  { id: '2', text: 'Quelles sont les conclusions principales ?' },
  { id: '3', text: 'Compare les différentes sources' },
];

interface SavedPromptSuggestionsProps {
  onSelect: (text: string) => void;
}

export const SavedPromptSuggestions = ({ onSelect }: SavedPromptSuggestionsProps) => {
  return (
    <div className="flex flex-wrap gap-2 mb-3 animate-fade-in">
      {SAVED_PROMPTS.map((prompt) => (
        <button
          key={prompt.id}
          onClick={() => onSelect(prompt.text)}
          className="group inline-flex items-center gap-2 px-3 py-2 text-xs rounded-xl
                     border border-border/60 bg-card/80 text-muted-foreground
                     hover:bg-secondary/60 hover:text-foreground hover:border-primary/20
                     hover:shadow-sm transition-all duration-200"
        >
          <MessageSquare className="w-3.5 h-3.5 shrink-0 text-primary/40 group-hover:text-primary/70 transition-colors" />
          <span>{prompt.text}</span>
        </button>
      ))}
    </div>
  );
};
