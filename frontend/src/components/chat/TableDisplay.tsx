import { useEffect, useMemo, useState } from 'react';
import { TablePagination } from '@/components/ui/table-pagination';
import { formatCellValue, isNumericColumn, type CellValue } from '@/lib/table-utils';
import { cn } from '@/lib/utils';

type TableRow = Record<string, CellValue>;

interface TableDisplayProps {
  data: TableRow[];
  columns?: string[];
  title?: string;
  className?: string;
  tableContainerClassName?: string;
  emptyLabel?: string;
  showRowCount?: boolean;
  maxRowsBeforePagination?: number;
}

export function TableDisplay({
  data,
  columns,
  title,
  className,
  tableContainerClassName,
  emptyLabel = 'No rows returned',
  showRowCount = true,
  maxRowsBeforePagination = 100,
}: TableDisplayProps) {
  const resolvedColumns =
    columns && columns.length > 0 ? columns : inferColumns(data);
  const numericColumns = new Set(
    resolvedColumns.filter((column) => isNumericColumn(data, column)),
  );
  const hasRows = data.length > 0;
  const needsPagination = data.length > maxRowsBeforePagination;

  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(maxRowsBeforePagination);

  useEffect(() => setPageIndex(0), [data]);

  const pageCount = Math.ceil(data.length / pageSize);
  const pageData = useMemo(
    () =>
      needsPagination
        ? data.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
        : data,
    [data, pageIndex, pageSize, needsPagination],
  );

  return (
    <div className={cn('flex flex-col gap-2 my-2', className)}>
      {title ? (
        <h4 className="text-sm font-medium text-foreground">{title}</h4>
      ) : null}

      <div
        className={cn(
          'rounded-lg border border-border overflow-auto bg-card',
          tableContainerClassName,
        )}
      >
        <table className="w-full text-sm border-collapse">
          <thead className="bg-muted sticky top-0">
            <tr>
              {resolvedColumns.map((column) => (
                <th
                  key={column}
                  className={cn(
                    'px-3 py-2 text-left font-medium text-xs uppercase tracking-wide text-muted-foreground border-b border-border whitespace-nowrap',
                    numericColumns.has(column) && 'text-right',
                  )}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {hasRows ? (
              pageData.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className="border-b border-border/50 last:border-0 hover:bg-muted/40 transition-colors"
                >
                  {resolvedColumns.map((column) => {
                    const value = row[column];
                    const isNull = value === null || value === undefined;
                    return (
                      <td
                        key={column}
                        className={cn(
                          'px-3 py-2 align-top text-foreground',
                          numericColumns.has(column) &&
                            'text-right tabular-nums',
                        )}
                      >
                        {isNull ? (
                          <span className="text-muted-foreground italic">
                            NULL
                          </span>
                        ) : (
                          formatCellValue(value)
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={resolvedColumns.length || 1}
                  className="px-3 py-6 text-center text-muted-foreground text-sm"
                >
                  {emptyLabel}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {needsPagination ? (
        <TablePagination
          pageIndex={pageIndex}
          pageCount={pageCount}
          pageSize={pageSize}
          totalRows={data.length}
          onPageChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPageIndex(0);
          }}
        />
      ) : showRowCount && hasRows ? (
        <div className="text-xs text-muted-foreground px-1">
          {data.length} {data.length === 1 ? 'row' : 'rows'}
        </div>
      ) : null}
    </div>
  );
}

function inferColumns(data: TableRow[]): string[] {
  const seen = new Set<string>();
  const columns: string[] = [];

  for (const row of data) {
    for (const column of Object.keys(row)) {
      if (seen.has(column)) continue;
      seen.add(column);
      columns.push(column);
    }
  }

  return columns;
}

export default TableDisplay;
