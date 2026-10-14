import React, { useEffect, useState } from 'react';
import { analystJobs, type AnalystJob } from '../../api/analystJobs';

interface Props {
  sourceId: string;
  onClose: () => void;
  onOpenRun: (runId: string) => void;
}

const STORAGE_KEY = 'quantai.temporal.last-job';
const terminalStates = new Set([
  'completed', 'rejected', 'expired', 'needs_clarification',
  'failed', 'canceled', 'cancelled', 'terminated', 'timed_out',
]);

export const DurableAnalysisDialog: React.FC<Props> = ({ sourceId, onClose, onOpenRun }) => {
  const [question, setQuestion] = useState('');
  const [includeReport, setIncludeReport] = useState(false);
  const [job, setJob] = useState<AnalystJob | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const previous = window.localStorage.getItem(STORAGE_KEY);
    if (!previous) return;
    let mounted = true;
    analystJobs.get(previous)
      .then((value) => { if (mounted) setJob(value); })
      .catch(() => { if (mounted) window.localStorage.removeItem(STORAGE_KEY); });
    return () => { mounted = false; };
  }, []);

  const jobId = job?.job_id;
  const finalStatus = job?.status || 'queued';
  const isFinished = terminalStates.has(finalStatus);

  useEffect(() => {
    if (!jobId || isFinished) return;
    let active = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const updated = await analystJobs.get(jobId);
        if (!active) return;
        setJob(updated);
        if (!terminalStates.has(updated.status)) {
          timer = window.setTimeout(tick, 2000);
        }
      } catch {
        if (active) timer = window.setTimeout(tick, 5000);
      }
    };
    timer = window.setTimeout(tick, 1000);
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [jobId, isFinished]);

  const start = async () => {
    if (!question.trim() || pending) return;
    setError(null);
    setPending(true);
    try {
      const created = await analystJobs.start(question.trim(), sourceId, includeReport);
      window.localStorage.setItem(STORAGE_KEY, created.job_id);
      setJob(created);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start job');
    } finally {
      setPending(false);
    }
  };

  const review = async (approved: boolean) => {
    if (!jobId || pending) return;
    setPending(true);
    setError(null);
    try {
      await analystJobs.review(jobId, approved);
      setJob((current) => current ? { ...current, status: 'running', stage: 'publication' } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Review failed');
    } finally {
      setPending(false);
    }
  };

  const cancel = async () => {
    if (!jobId || pending) return;
    setPending(true);
    try {
      await analystJobs.cancel(jobId);
      setJob((current) => current ? { ...current, status: 'cancellation_requested' } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Cancellation failed');
    } finally {
      setPending(false);
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-label="Durable analyst workflow"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-[#0f1420] p-6 text-slate-100 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Durable multi-agent analysis</h2>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              Temporal tracks specialist agents, retries, validation and review.
              Results are stored in local analysis history.
            </p>
          </div>
          <button type="button" onClick={onClose}
            aria-label="Close analyst dialog" className="rounded-lg px-3 py-1 text-slate-300 hover:bg-white/10">
            Close
          </button>
        </div>

        {!job ? (
          <form className="mt-5 space-y-3" onSubmit={(event) => { event.preventDefault(); void start(); }}>
            <label htmlFor="analyst-question" className="block text-sm font-medium">Analysis question</label>
            <textarea id="analyst-question" rows={4} maxLength={2000} value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="For example: Compare sales by region, explain the biggest drivers and assess data quality."
              className="w-full rounded-xl border border-white/10 bg-[#070b12] p-3 text-sm outline-none focus:border-indigo-400" />
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={includeReport} onChange={(event) => setIncludeReport(event.target.checked)} />
              Prepare a PDF report after approval
            </label>
            <button type="submit" disabled={pending || !question.trim()}
              className="btn-primary rounded-xl px-5 py-2 disabled:opacity-50">
              {pending ? 'Starting…' : 'Start durable analysis'}
            </button>
          </form>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <p className="text-xs uppercase tracking-wide text-slate-400">Job status</p>
              <p role="status" className="mt-1 font-semibold capitalize">
                {finalStatus.replace(/_/g, ' ')}
              </p>
              {job.stage && <p className="mt-1 text-xs text-slate-300">Stage: {job.stage.replace(/_/g, ' ')}</p>}
              {!!job.completed_stages?.length && (
                <ol className="mt-3 space-y-1 text-xs text-emerald-200" aria-label="Completed specialist stages">
                  {job.completed_stages.map((stage) => (
                    <li key={stage}>✓ {stage.replace(/_/g, ' ')}</li>
                  ))}
                </ol>
              )
              <p className="mt-2 break-all text-[11px] text-slate-500">{jobId}</p>
            </div>
            {job.review_reasons && job.review_reasons.length > 0 && (
              <div className="rounded-xl border border-amber-400/25 bg-amber-400/[0.05] p-4">
                <p className="text-sm font-semibold text-amber-200">Human review required</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-300">
                  {job.review_reasons.map((reason, index) => <li key={index}>{reason}</li>)}
                </ul>
              </div>
            )}
            {finalStatus === 'waiting_for_approval' && (
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-primary px-4 py-2" disabled={pending}
                  onClick={() => void review(true)}>Approve</button>
                <button type="button" className="btn-ghost px-4 py-2" disabled={pending}
                  onClick={() => void review(false)}>Reject</button>
              </div>
            )}
            {finalStatus === 'completed' && job.report?.status === 'failed' && (
              <p role="alert" className="text-sm text-amber-200">
                {job.report.reason || 'Your approved analysis is saved, but the report could not be generated.'}
              </p>
            )}
            {finalStatus === 'completed' && job.report?.status === 'ready' && job.report.download_url && (
              <a href={job.report.download_url} className="btn-ghost inline-flex px-4 py-2 text-xs">
                Export approved report
              </a>
            )}
            {finalStatus === 'completed' && job.run_id && (
              <button type="button" className="btn-primary px-4 py-2"
                onClick={() => { onOpenRun(job.run_id!); onClose(); }}>
                Open verified result
              </button>
            )}
            {!isFinished && finalStatus !== 'cancellation_requested' && (
              <button type="button" className="btn-ghost px-4 py-2" disabled={pending}
                onClick={() => void cancel()}>Cancel job</button>
            )}
            {isFinished && (
              <button type="button" className="btn-ghost px-4 py-2"
                onClick={() => {
                  window.localStorage.removeItem(STORAGE_KEY);
                  setJob(null);
                  setQuestion('');
                }}>Start another analysis</button>
            )}
          </div>
        )}
        {error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
      </div>
    </div>
  );
};
