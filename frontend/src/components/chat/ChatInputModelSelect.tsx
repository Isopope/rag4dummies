import { Bot, BrainCircuit, Gem, Sparkles, Zap } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface ChatModel {
  id: string;
  name: string;
  provider: string;
}

export const MOCK_MODELS: ChatModel[] = [
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai' },
  { id: 'gpt-4o-mini', name: 'GPT-4o mini', provider: 'openai' },
  { id: 'claude-sonnet-4', name: 'Claude Sonnet 4', provider: 'anthropic' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'google' },
];

const PROVIDER_META = {
  openai: { label: 'OpenAI', icon: Bot },
  anthropic: { label: 'Anthropic', icon: BrainCircuit },
  google: { label: 'Google', icon: Gem },
} as const;

function getProviderMeta(provider: string) {
  return PROVIDER_META[provider as keyof typeof PROVIDER_META] ?? { label: provider, icon: Zap };
}

interface ChatInputModelSelectProps {
  value: string;
  onChange: (id: string) => void;
}

export function ChatInputModelSelect({ value, onChange }: ChatInputModelSelectProps) {
  const selected = MOCK_MODELS.find((m) => m.id === value) ?? MOCK_MODELS[0];
  const selectedMeta = getProviderMeta(selected.provider);
  const SelectedIcon = selectedMeta.icon;

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-7 w-auto gap-1.5 border-none bg-transparent px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted focus:ring-0 focus:ring-offset-0 [&>svg]:size-3">
        <SelectedIcon className="size-3 shrink-0" />
        <SelectValue>{selected.name}</SelectValue>
      </SelectTrigger>
      <SelectContent align="end">
        {MOCK_MODELS.map((m) => {
          const meta = getProviderMeta(m.provider);
          const ProviderIcon = meta.icon;

          return (
            <SelectItem key={m.id} value={m.id} className="text-xs">
              <div className="flex items-center gap-2">
                <ProviderIcon className="size-3.5 shrink-0 text-muted-foreground" />
                <div className="flex flex-col">
                  <span>{m.name}</span>
                  <span className="text-[10px] text-muted-foreground">{meta.label}</span>
                </div>
              </div>
            </SelectItem>
          );
        })}
        <div className="px-2 py-1.5 text-[10px] text-muted-foreground border-t border-border">
          <div className="flex items-center gap-1.5">
            <Sparkles className="size-3" />
            Providers mockés pour la prévisualisation
          </div>
        </div>
      </SelectContent>
    </Select>
  );
}
