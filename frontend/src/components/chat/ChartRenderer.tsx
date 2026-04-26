import { useMemo, useRef, useState } from 'react';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Download, TrendingDown, TrendingUp } from 'lucide-react';
import html2canvas from 'html2canvas';
import { ChartData } from '@/types/chat';
import { Button } from '@/components/ui/button';
import { DisplayChartSeriesToggle } from './DisplayChartSeriesToggle';
import { ChartRangeSelector } from './ChartRangeSelector';
import {
  DATE_RANGE_OPTIONS,
  filterByDateRange,
  formatNumber,
  labelize,
  sortByDateKey,
  type DateRange,
} from '@/lib/charts.utils';

const CHART_COLORS = [
  'hsl(190, 80%, 42%)',
  'hsl(210, 80%, 55%)',
  'hsl(152, 60%, 42%)',
  'hsl(38, 92%, 50%)',
  'hsl(280, 60%, 55%)',
  'hsl(0, 72%, 51%)',
];

interface ChartRendererProps {
  chartData: ChartData;
}

const KpiCard = ({ chartData }: { chartData: ChartData }) => {
  const { title, data, kpi } = chartData;
  const valueKey = kpi?.valueKey ?? chartData.yKeys[0];
  const raw = data[0]?.[valueKey];
  const numeric = typeof raw === 'number' ? raw : Number(raw);
  const display = Number.isFinite(numeric) ? formatNumber(numeric) : String(raw ?? '—');
  const variation = kpi?.variation;
  const isPositive = (variation ?? 0) >= 0;

  return (
    <div className="my-3 p-5 rounded-lg border border-border bg-card">
      {(kpi?.label || title) && (
        <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
          {kpi?.label || title}
        </p>
      )}
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="text-3xl font-semibold text-foreground tabular-nums">
          {display}
          {kpi?.unit && <span className="text-lg text-muted-foreground ml-1">{kpi.unit}</span>}
        </span>
        {variation !== undefined && (
          <span
            className={`inline-flex items-center gap-1 text-sm font-medium ${
              isPositive ? 'text-[hsl(152,60%,42%)]' : 'text-destructive'
            }`}
          >
            {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            {(variation * 100).toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
};

const ChartRenderer = ({ chartData }: ChartRendererProps) => {
  const { type, title, xKey, yKeys, colors, xKeyType } = chartData;
  const chartColors = colors || CHART_COLORS;
  const containerRef = useRef<HTMLDivElement>(null);

  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [range, setRange] = useState<DateRange>('all');

  const series = useMemo(
    () => yKeys.map((k) => ({ dataKey: k, label: labelize(k) })),
    [yKeys],
  );

  const visibleSeriesMap = useMemo(
    () => Object.fromEntries(yKeys.map((k) => [k, !hidden.has(k)])),
    [yKeys, hidden],
  );

  const visibleYKeys = useMemo(
    () => yKeys.filter((k) => !hidden.has(k)),
    [yKeys, hidden],
  );

  const handleToggle = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const processedData = useMemo(() => {
    if (xKeyType !== 'date') return chartData.data;
    const sorted = sortByDateKey(chartData.data, xKey);
    return filterByDateRange(sorted, xKey, range);
  }, [chartData.data, xKey, xKeyType, range]);

  const handleDownload = async () => {
    if (!containerRef.current) return;
    try {
      const canvas = await html2canvas(containerRef.current, {
        backgroundColor: getComputedStyle(document.body).backgroundColor || '#ffffff',
        scale: 2,
      });
      const link = document.createElement('a');
      link.download = `${title || 'chart'}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('Error downloading chart image:', err);
    }
  };

  if (type === 'kpi_card') {
    return <KpiCard chartData={chartData} />;
  }

  const renderChart = () => {
    switch (type) {
      case 'bar':
        return (
          <BarChart data={processedData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 13%, 90%)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <YAxis tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(220, 13%, 90%)', fontSize: '12px' }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            {visibleYKeys.map((key) => (
              <Bar key={key} dataKey={key} fill={chartColors[yKeys.indexOf(key) % chartColors.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        );

      case 'line':
        return (
          <LineChart data={processedData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 13%, 90%)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <YAxis tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(220, 13%, 90%)', fontSize: '12px' }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            {visibleYKeys.map((key) => (
              <Line key={key} type="monotone" dataKey={key} stroke={chartColors[yKeys.indexOf(key) % chartColors.length]} strokeWidth={2} dot={{ r: 4 }} />
            ))}
          </LineChart>
        );

      case 'area':
        return (
          <AreaChart data={processedData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 13%, 90%)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <YAxis tick={{ fontSize: 12 }} stroke="hsl(220, 10%, 50%)" />
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(220, 13%, 90%)', fontSize: '12px' }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            {visibleYKeys.map((key) => (
              <Area key={key} type="monotone" dataKey={key} stroke={chartColors[yKeys.indexOf(key) % chartColors.length]} fill={chartColors[yKeys.indexOf(key) % chartColors.length]} fillOpacity={0.15} strokeWidth={2} />
            ))}
          </AreaChart>
        );

      case 'pie':
        return (
          <PieChart>
            <Pie data={processedData} dataKey={visibleYKeys[0] ?? yKeys[0]} nameKey={xKey} cx="50%" cy="50%" outerRadius={80} label>
              {processedData.map((_, i) => (
                <Cell key={i} fill={chartColors[i % chartColors.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(220, 13%, 90%)', fontSize: '12px' }} />
          </PieChart>
        );

      default:
        return null;
    }
  };

  const showSeriesToggle = type !== 'pie' && yKeys.length > 1;
  const showRangeSelector = type !== 'pie' && xKeyType === 'date';

  return (
    <div ref={containerRef} className="my-3 p-4 rounded-lg border border-border bg-card">
      <div className="flex items-start justify-between gap-2 mb-3 flex-wrap">
        {title ? (
          <h4 className="text-sm font-semibold text-card-foreground">{title}</h4>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-1.5">
          {showRangeSelector && (
            <ChartRangeSelector
              options={DATE_RANGE_OPTIONS}
              selectedRange={range}
              onRangeSelected={(r) => setRange(r as DateRange)}
            />
          )}
          {showSeriesToggle && (
            <DisplayChartSeriesToggle
              series={series}
              visibleSeries={visibleSeriesMap}
              onToggle={handleToggle}
            />
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleDownload}
            aria-label="Télécharger le graphique"
            title="Télécharger en PNG"
          >
            <Download className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
      <div className="w-full h-64">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()!}
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ChartRenderer;
