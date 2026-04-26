import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { labelize } from '@/lib/charts.utils';

interface DisplayChartSeriesToggleProps {
  series: { dataKey: string; label?: string }[];
  visibleSeries: Record<string, boolean>;
  onToggle: (dataKey: string) => void;
}

export function DisplayChartSeriesToggle({
  series,
  visibleSeries,
  onToggle,
}: DisplayChartSeriesToggleProps) {
  const visibleCount = Object.values(visibleSeries).filter(Boolean).length;
  const totalCount = series.length;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1">
          Séries ({visibleCount}/{totalCount})
          <ChevronDown className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {series.map((s) => (
          <DropdownMenuCheckboxItem
            key={s.dataKey}
            checked={visibleSeries[s.dataKey] ?? true}
            onCheckedChange={() => onToggle(s.dataKey)}
          >
            {s.label || labelize(s.dataKey)}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
