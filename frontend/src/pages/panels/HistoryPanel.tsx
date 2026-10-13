/**
 * Query history with open, re-run, and delete actions.
 */
import React, { useEffect, useState } from 'react';
import { History, CheckCircle2, XCircle, Trash2, RotateCcw, Clock, ArrowUpRight, Loader2 } from 'lucide-react';
import { api } from '../../api/client';
import { useAppStore } from '../../store/useAppStore';
import { DEMO_HISTORY } from '../../api/demo';
import type { HistoryRun } from '../../api/client';

interface Props {
  onRerun: (question: string) => void;
  onOpen: (runId: string) => Promise<void>;
}

export const HistoryPanel: React.FC<Props> = ({ onRerun, onOpen }) => {
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const { demoMode, backendReachable } = useAppStore();

  useEffect(() => {
    let active = true;
    setLoading(true);
    if (demoMode || !backendReachable) {
      setRuns(DEMO_HISTORY);
      setLoading(false);
      return () => { active = false; };
    }
    api.history.list(50)
      .then((items) => { if (active) setRuns(items); })
      .catch(() => { if (active) setRuns([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [demoMode, backendReachable]);

  const handleDelete = async (id: string) => {
    try {
      if (!demoMode) await api.history.delete(id);
      setRuns((prev) => prev.filter((run) => run.id !== id));
    } catch {
      setOpenError('This history item could not be deleted. Please try again.');
    }
  };

  const handleOpen = async (id: string) => {
    setOpeningId(id);
    setOpenError(null);
    try {
      if (demoMode || !backendReachable) {
        const selected = runs.find((run) => run.id === id);
        if (selected) onRerun(selected.question);
        return;
      }
      await onOpen(id);
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : 'This history item could not be opened. Please try again.');
    } finally {
      setOpeningId(null);
    }
  };

  const formatTime = (iso: string) => {
    const date = new Date(iso);
    const diff = Date.now() - date.getTime();
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <History className="w-5 h-5 text-indigo-400" />
        <h2 className="text-lg font-bold text-white">Query History</h2>
        <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-xs">{runs.length}</span>
      </div>

      {openError && (
        <div role="alert" className="mb-4 rounded-xl border border-red-400/20 bg-red-400/[0.06] px-4 py-3 text-sm text-red-300">
          {openError}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-20 shimmer rounded-2xl" />)}
        </div>
      ) : runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
          <History className="w-12 h-12 text-slate-700" />
          <p className="text-slate-500">No query history yet.</p>
          <p className="text-slate-600 text-sm">Your queries will appear here.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {runs.map((run, i) => (
            <div
              key={run.id}
              className="glass-hover rounded-2xl p-3 sm:p-4 flex items-start gap-2 sm:gap-3 group animate-fade-in-up"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <button
                type="button"
                onClick={() => handleOpen(run.id)}
                disabled={openingId !== null}
                aria-label={`Open saved answer: ${run.question}`}
                className="flex min-w-0 flex-1 items-start gap-3 sm:gap-4 rounded-xl text-left outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 disabled:cursor-wait"
              >
                <div className="shrink-0 mt-0.5">
                  {openingId === run.id
                    ? <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
                    : run.status === 'success'
                      ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      : <XCircle className="w-5 h-5 text-red-400" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 font-medium leading-snug">{run.question}</p>
                  <div className="flex flex-wrap items-center gap-3 mt-2">
                    <span className="flex items-center gap-1 text-[11px] text-slate-600">
                      <Clock className="w-3 h-3" />{formatTime(run.created_at)}
                    </span>
                    {run.confidence && (
                      <span className={`text-[11px] font-medium ${run.confidence === 'High' ? 'text-emerald-400' : run.confidence === 'Medium' ? 'text-amber-400' : 'text-red-400'}`}>
                        {run.confidence}
                      </span>
                    )}
                    {run.row_count != null && <span className="text-[11px] text-slate-600">{run.row_count.toLocaleString()} rows</span>}
                    {run.verified && <span className="text-[11px] text-emerald-400">? Verified</span>}
                  </div>
                </div>
                <span className="mt-0.5 flex shrink-0 items-center gap-1 text-xs font-medium text-indigo-400">
                  Open <ArrowUpRight className="h-3.5 w-3.5" />
                </span>
              </button>

              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onRerun(run.question)}
                  className="p-2 rounded-lg text-slate-500 hover:text-indigo-400 hover:bg-slate-800 transition-all"
                  title="Re-run this query"
                  aria-label="Re-run this query"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleDelete(run.id)}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-slate-800 transition-all"
                  title="Delete"
                  aria-label="Delete history item"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
