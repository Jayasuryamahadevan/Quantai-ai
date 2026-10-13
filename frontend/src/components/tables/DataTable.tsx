/**
 * components/tables/DataTable.tsx — Virtualized data table for query results.
 */
import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Download } from 'lucide-react';

interface Props {
  rows: Record<string, any>[];
  columns: string[];
  total_rows?: number;
  run_id?: string;
  className?: string;
}

const PAGE_SIZE = 25;

function formatCell(value: any): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function cellClass(value: any): string {
  if (value === null || value === undefined) return 'text-slate-600 italic';
  if (typeof value === 'number') return 'text-right tabular-nums text-sky-300/90';
  if (typeof value === 'boolean') return value ? 'text-emerald-400' : 'text-red-400';
  return '';
}

export const DataTable: React.FC<Props> = ({ rows, columns, total_rows, run_id, className }) => {
  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const exportCsv = () => {
    if (run_id) {
      window.open(`http://localhost:8000/api/export/${run_id}?format=csv`, '_blank');
      return;
    }
    // Client-side CSV fallback
    const header = columns.join(',');
    const body = rows.map((r) => columns.map((c) => JSON.stringify(r[c] ?? '')).join(',')).join('\n');
    const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'quantai_result.csv';
    a.click();
  };

  return (
    <div className={`rounded-xl overflow-hidden border border-slate-800/60 ${className || ''}`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/80 border-b border-slate-800/60">
        <span className="text-xs text-slate-400 font-medium">
          {rows.length < (total_rows || 0)
            ? `Showing ${rows.length.toLocaleString()} of ${(total_rows || 0).toLocaleString()} rows`
            : `${rows.length.toLocaleString()} rows · ${columns.length} columns`}
        </span>
        <button
          onClick={exportCsv}
          className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors font-medium"
        >
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="data-table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col} title={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri}>
                {columns.map((col) => (
                  <td key={col} className={cellClass(row[col])} title={formatCell(row[col])}>
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 px-4 py-2.5 bg-slate-900/80 border-t border-slate-800/60">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-400">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
