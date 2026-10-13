/**
 * components/ui/StepTracker.tsx — Shows live agent pipeline progress.
 */
import React from 'react';
import {
  Brain, Database, Columns, GitGraph, Code2,
  Play, CheckCircle2, BarChart3, Sparkles, TrendingUp, ShieldCheck, Loader2
} from 'lucide-react';

const STEPS: { id: string; label: string; icon: React.ElementType }[] = [
  { id: 'supervisor', label: 'Supervisor', icon: Brain },
  { id: 'source_resolver', label: 'Source', icon: Database },
  { id: 'column_selector', label: 'Columns', icon: Columns },
  { id: 'query_planner', label: 'Planning', icon: GitGraph },
  { id: 'sql_compile', label: 'SQL', icon: Code2 },
  { id: 'validate_execute', label: 'Execute', icon: Play },
  { id: 'cross_check', label: 'Verify', icon: ShieldCheck },
  { id: 'cleaner', label: 'Clean', icon: CheckCircle2 },
  { id: 'stats_analyzer', label: 'Stats', icon: TrendingUp },
  { id: 'visualizer', label: 'Chart', icon: BarChart3 },
  { id: 'insight', label: 'Insight', icon: Sparkles },
];

interface Props {
  currentStep: string;
  completedSteps: string[];
}

export const StepTracker: React.FC<Props> = ({ currentStep, completedSteps }) => {
  return (
    <div className="step-tracker flex flex-wrap gap-1.5 p-3 rounded-xl bg-slate-900/60 border border-slate-800/60">
      {STEPS.map(({ id, label, icon: Icon }) => {
        const isDone = completedSteps.includes(id);
        const isActive = currentStep === id && !isDone;

        return (
          <div
            key={id}
            className={`step-indicator ${isDone ? 'done' : isActive ? 'active' : 'pending'}`}
          >
            {isActive ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : isDone ? (
              <CheckCircle2 className="w-3 h-3" />
            ) : (
              <Icon className="w-3 h-3" />
            )}
            <span>{label}</span>
          </div>
        );
      })}
    </div>
  );
};
