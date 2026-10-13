/**
 * components/chat/MessageBubble.tsx — A single chat message with all result panels.
 */
import React, { lazy, Suspense, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  ChevronDown, ChevronUp, Code2, BarChart3,
  ShieldAlert, ThumbsUp, ThumbsDown, Download,
  AlertTriangle, CheckCircle2, Clock, Cpu, Sparkles, Loader2
} from 'lucide-react';
import { DataTable } from '../tables/DataTable';
import { StepTracker } from '../ui/StepTracker';
import type { ChatMessage } from '../../store/useAppStore';
import { api } from '../../api/client';

const PlotlyChart = lazy(() =>
  import('../charts/PlotlyChart').then((module) => ({ default: module.PlotlyChart })),
);

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
  activeStep?: string;
  completedSteps?: string[];
}

function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;
  const cls = confidence === 'High' ? 'high' : confidence === 'Medium' ? 'medium' : 'low';
  return <span className={`confidence-badge ${cls}`}>{confidence} Confidence</span>;
}

function VerifiedBadge({ verified }: { verified?: boolean }) {
  if (verified === undefined) return null;
  return verified ? (
    <span className="confidence-badge high"><CheckCircle2 className="w-3 h-3" /> Verified</span>
  ) : (
    <span className="confidence-badge low"><ShieldAlert className="w-3 h-3" /> Unverified</span>
  );
}

export const MessageBubble: React.FC<Props> = ({
  message, isStreaming, activeStep, completedSteps = []
}) => {
  const [showSql, setShowSql] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const [feedback, setFeedback] = useState<1 | -1 | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const isUser = message.role === 'user';

  const handleFeedback = async (value: 1 | -1) => {
    if (!message.run_id || feedback === value) return;
    setFeedback(value);
    try {
      await api.feedback(message.run_id, value);
    } catch { /* ignore */ }
  };

  const handleDownload = async (download: () => Promise<void>) => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await download();
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Download failed. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in-up">
        <div className="max-w-[78%] px-5 py-3.5 rounded-2xl rounded-br-md bg-indigo-500/15 border border-indigo-300/15 text-slate-100 shadow-[0_10px_30px_rgba(15,23,42,0.18)]">
          <p className="text-sm leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex w-full min-w-0 flex-col items-start gap-3 animate-fade-in-up">
      {/* Step tracker during streaming */}
      {isStreaming && activeStep && (
        <StepTracker currentStep={activeStep} completedSteps={completedSteps} />
      )}

      {/* Main answer bubble */}
      {message.content && (
        <div className="assistant-answer-card w-full rounded-[22px] border border-white/[0.075] bg-[#10141e]/90 shadow-[0_18px_55px_rgba(0,0,0,0.16)] overflow-hidden">
          <div className="assistant-answer-header flex items-center justify-between px-5 sm:px-6 py-3.5 border-b border-white/[0.055]">
            <div className="flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-indigo-400/10 border border-indigo-300/10 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-indigo-300" />
              </span>
              <span className="text-[10px] uppercase tracking-[0.17em] font-semibold text-slate-400">Quantai insight</span>
            </div>
            <span className="text-[10px] text-slate-600 hidden sm:block">Local analysis</span>
          </div>
          <div className="px-5 sm:px-6 py-5">
            <ReactMarkdown
              className="prose prose-invert prose-sm max-w-none
                         prose-headings:text-slate-100 prose-headings:font-semibold prose-headings:tracking-tight
                         prose-h2:text-lg prose-h2:mt-0 prose-h2:mb-3 prose-h3:text-sm prose-h3:uppercase prose-h3:tracking-wider prose-h3:text-slate-400
                         prose-p:text-slate-300 prose-p:leading-7 prose-p:my-2.5
                         prose-strong:text-slate-100 prose-code:text-indigo-300 prose-code:bg-indigo-500/10
                         prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
                         prose-li:text-slate-300 prose-li:my-1.5 prose-a:text-indigo-400
                         prose-ul:my-3 prose-ol:my-3 prose-hr:border-white/10"
            >
              {message.content}
            </ReactMarkdown>

          {/* Badges */}
          {message.status === 'done' && (message.confidence || message.verified !== undefined) && (
            <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-white/[0.06]">
              <ConfidenceBadge confidence={message.confidence} />
              <VerifiedBadge verified={message.verified} />
              {message.is_fallback_sql && (
                <span className="confidence-badge medium">
                  <AlertTriangle className="w-3 h-3" /> Fallback SQL
                </span>
              )}
            </div>
          )}
          </div>
        </div>
      )}

      {/* Warnings */}
      {message.warnings && message.warnings.length > 0 && (
        <div className="max-w-[90%] px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/20">
          {message.warnings.map((w, i) => (
            <p key={i} className="text-amber-300 text-xs flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {w}
            </p>
          ))}
        </div>
      )}

      {/* Errors */}
      {message.errors && message.errors.length > 0 && message.status === 'error' && (
        <div className="max-w-[90%] px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20">
          {message.errors.map((e, i) => (
            <p key={i} className="text-red-300 text-xs">{e}</p>
          ))}
        </div>
      )}

      {/* Chart */}
      {message.chart && (
        <div className="glass w-full min-w-0 rounded-2xl p-4 animate-scale-in">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
              {message.chart_type || 'Chart'}
            </span>
          </div>
          <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-slate-800/40" />}>
            <PlotlyChart chart={message.chart} />
          </Suspense>
        </div>
      )}

      {/* Data Table */}
      {message.rows && message.rows.length > 0 && message.columns && (
        <div className="animate-scale-in max-w-full">
          <DataTable
            rows={message.rows}
            columns={message.columns}
            total_rows={message.total_rows}
            run_id={message.run_id}
          />
        </div>
      )}

      {/* SQL Accordion */}
      {message.sql && (
        <div className="max-w-[90%] animate-fade-in">
          <button
            onClick={() => setShowSql(!showSql)}
            className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 transition-colors mb-1.5"
          >
            <Code2 className="w-3.5 h-3.5" />
            {showSql ? 'Hide' : 'Show'} Generated SQL
            {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showSql && (
            <pre className="sql-block">{message.sql}</pre>
          )}
        </div>
      )}

      {/* Action row */}
      {message.status === 'done' && (message.run_id || message.is_document_answer) && (
        <div className="flex items-center gap-3 max-w-[90%] flex-wrap">
          {/* Feedback */}
          {message.run_id && <div className="flex items-center gap-1">
            <button
              onClick={() => handleFeedback(1)}
              className={`p-1.5 rounded-lg transition-colors ${feedback === 1 ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-600 hover:text-slate-300'}`}
              title="Good answer"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleFeedback(-1)}
              className={`p-1.5 rounded-lg transition-colors ${feedback === -1 ? 'bg-red-500/20 text-red-400' : 'text-slate-600 hover:text-slate-300'}`}
              title="Needs improvement"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>}

          {/* Export buttons */}
          {message.run_id && message.sql && (
            <div className="flex items-center gap-1">
              {['csv', 'xlsx', 'pdf'].map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => handleDownload(() => api.export(message.run_id!, fmt))}
                  disabled={downloading}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-50 transition-colors font-medium"
                >
                  <Download className="w-3 h-3" />
                  {fmt.toUpperCase()}
                </button>
              ))}
            </div>
          )}

          {(message.is_document_answer || (message.run_id && !message.sql)) && (
            <button
              onClick={() => handleDownload(() => api.exportDocumentReport(message.content, 'pdf'))}
              disabled={downloading}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-50 transition-colors font-medium"
            >
              {downloading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
              {downloading ? 'Preparing PDF' : 'Download PDF'}
            </button>
          )}

          {/* Trace toggle */}
          {message.run_id && message.trace && message.trace.length > 0 && (
            <button
              onClick={() => setShowTrace(!showTrace)}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              <Cpu className="w-3 h-3" />
              {showTrace ? 'Hide' : 'Show'} Trace
              {showTrace ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {downloadError && <p role="alert" className="w-full text-xs text-red-300">{downloadError}</p>}
        </div>
      )}

      {/* Execution Trace */}
      {showTrace && message.trace && (
        <div className="max-w-[90%] glass rounded-xl p-3 animate-scale-in">
          <p className="text-xs text-slate-500 font-medium mb-2 uppercase tracking-wider">Execution Trace</p>
          <div className="space-y-1">
            {message.trace.map((step: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-slate-300 font-mono">{step.step}</span>
                <div className="flex items-center gap-2">
                  {step.status === 'completed' ? (
                    <span className="text-emerald-400 text-[10px]">✓ {step.status}</span>
                  ) : step.status === 'error' ? (
                    <span className="text-red-400 text-[10px]">✗ error</span>
                  ) : (
                    <span className="text-amber-400 text-[10px]">{step.status}</span>
                  )}
                  {step.duration_ms && (
                    <span className="text-slate-600 flex items-center gap-0.5">
                      <Clock className="w-2.5 h-2.5" />
                      {step.duration_ms}ms
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
