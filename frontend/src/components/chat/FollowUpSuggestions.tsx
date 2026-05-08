import { ArrowUpRight } from 'lucide-react';

interface FollowUpSuggestionsProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
}

const FollowUpSuggestions = ({ suggestions, onSelect }: FollowUpSuggestionsProps) => {
  if (!suggestions.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mt-1 animate-fade-in">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion}
          onClick={() => onSelect(suggestion)}
          className="group inline-flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-full
                     border border-border/70 bg-card/80 backdrop-blur-sm text-foreground
                     hover:bg-accent hover:text-accent-foreground hover:border-accent
                     transition-all duration-200 font-medium shadow-sm"
        >
          <span className="truncate max-w-[16rem]">{suggestion}</span>
          <ArrowUpRight className="w-3 h-3 shrink-0 opacity-0 -translate-x-1 group-hover:opacity-60 group-hover:translate-x-0 transition-all duration-200" />
        </button>
      ))}
    </div>
  );
};

export default FollowUpSuggestions;
