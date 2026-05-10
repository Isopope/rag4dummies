import { useEffect, useState } from 'react';
import { GitBranch, Workflow } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getAgentEngines } from '@/lib/api';
import type { AgentEngineInfo } from '@/lib/api';

interface ChatInputRuntimeSelectProps {
  value: string;
  onChange: (id: string) => void;
}

const ENGINE_ICONS: Record<string, React.ElementType> = {
  legacy_langgraph: GitBranch,
  react_runtime_v2: Workflow,
};

export function ChatInputRuntimeSelect({ value, onChange }: ChatInputRuntimeSelectProps) {
  const [engines, setEngines] = useState<AgentEngineInfo[]>([]);
  const [defaultEngine, setDefaultEngine] = useState('');

  useEffect(() => {
    getAgentEngines()
      .then(({ engines: list, default_stream: defaultStream }) => {
        setEngines(list);
        setDefaultEngine(defaultStream);
        if (!value && defaultStream) onChange(defaultStream);
      })
      .catch(() => {/* silencieux si API indisponible */});
  }, [onChange, value]);

  const currentId = value || defaultEngine;
  const current = engines.find((engine) => engine.id === currentId);
  const CurrentIcon = ENGINE_ICONS[currentId] ?? Workflow;

  if (engines.length === 0) return null;

  return (
    <Select value={currentId} onValueChange={onChange}>
      <SelectTrigger className="h-7 w-auto gap-1.5 border-none bg-transparent px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted focus:ring-0 focus:ring-offset-0 [&>svg]:size-3">
        <CurrentIcon className="size-3 shrink-0" />
        <SelectValue placeholder="Choisir un runtime">
          {current?.label ?? currentId}
        </SelectValue>
      </SelectTrigger>
      <SelectContent align="end">
        {engines.map((engine) => {
          const Icon = ENGINE_ICONS[engine.id] ?? Workflow;
          return (
            <SelectItem key={engine.id} value={engine.id} className="text-xs">
              <span className="inline-flex items-center gap-2">
                <Icon className="size-3" />
                {engine.label}
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
