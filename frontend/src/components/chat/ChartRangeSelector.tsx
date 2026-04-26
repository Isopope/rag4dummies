import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RangeOptions } from '@/lib/charts.utils';

interface Props<T extends RangeOptions> {
  selectedRange: keyof T;
  options: T;
  onRangeSelected: (range: keyof T) => void;
}

export function ChartRangeSelector<T extends RangeOptions>({
  options,
  selectedRange,
  onRangeSelected,
}: Props<T>) {
  return (
    <Select
      value={selectedRange as string}
      onValueChange={(v) => onRangeSelected(v as keyof T)}
    >
      <SelectTrigger className="h-7 w-[110px] text-xs">
        <SelectValue>{options[selectedRange].label}</SelectValue>
      </SelectTrigger>
      <SelectContent align="end" position="item-aligned">
        {Object.entries(options).map(([key, value]) => (
          <SelectItem key={key} value={key} className="text-xs">
            {value.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
