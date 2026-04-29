import { useEffect, useState } from 'react';
import { Bot, BrainCircuit, Gem, Zap, Cpu } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getModels } from '@/lib/api';
import type { ModelInfo } from '@/lib/api';

const PROVIDER_META: Record<string, { label: string; Icon: React.ElementType }> = {
  openai:     { label: 'OpenAI',      Icon: Bot },
  anthropic:  { label: 'Anthropic',   Icon: BrainCircuit },
  vertex_ai:  { label: 'Google',      Icon: Gem },
  openrouter: { label: 'OpenRouter',  Icon: Cpu },
};

function providerMeta(provider: string) {
  return PROVIDER_META[provider] ?? { label: provider, Icon: Zap };
}

interface ChatInputModelSelectProps {
  value: string;
  onChange: (id: string) => void;
  autoSelectDefault?: boolean;
  placeholder?: string;
}

export function ChatInputModelSelect({
  value,
  onChange,
  autoSelectDefault = true,
  placeholder,
}: ChatInputModelSelectProps) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState('');

  useEffect(() => {
    getModels()
      .then(({ models: list, default: def }) => {
        setModels(list);
        if (autoSelectDefault && !value && def) onChange(def);
        setDefaultModel(def);
      })
      .catch(() => {/* silencieux si API indisponible */});
  }, [autoSelectDefault, onChange, value]);

  // Groupe par provider
  const grouped = models.reduce<Record<string, ModelInfo[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});

  const currentId = value || (autoSelectDefault ? defaultModel : '');
  const current = models.find((m) => m.id === currentId);
  const { Icon: CurrentIcon } = providerMeta(current?.provider ?? '');

  if (models.length === 0) return null;

  return (
    <Select value={currentId} onValueChange={onChange}>
      <SelectTrigger className="h-7 w-auto gap-1.5 border-none bg-transparent px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted focus:ring-0 focus:ring-offset-0 [&>svg]:size-3">
        {current ? <CurrentIcon className="size-3 shrink-0" /> : <Zap className="size-3 shrink-0" />}
        <SelectValue placeholder={placeholder ?? 'Choisir un modele'}>
          {current?.label ?? currentId}
        </SelectValue>
      </SelectTrigger>
      <SelectContent align="end" className="max-h-72">
        {Object.entries(grouped).map(([provider, items]) => {
          const { label: provLabel, Icon: ProvIcon } = providerMeta(provider);
          return (
            <SelectGroup key={provider}>
              <SelectLabel className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                <ProvIcon className="size-3" />
                {provLabel}
              </SelectLabel>
              {items.map((m) => (
                <SelectItem key={m.id} value={m.id} className="text-xs pl-6">
                  {m.label}
                </SelectItem>
              ))}
            </SelectGroup>
          );
        })}
      </SelectContent>
    </Select>
  );
}
