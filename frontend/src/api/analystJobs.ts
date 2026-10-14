/** Temporal analysis job protocol (small metadata, no raw DataFrames). */
const BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export interface AnalystJob {
  job_id: string;
  run_id?: string;
  status: string;
  execution_status?: string;
  stage?: string;
  completed_stages?: string[];
  review_reasons?: string[];
  review?: { outcome: string; reasons: string[] };
  publication?: { status: string; history_path: string };
  report?: { status: string; download_url?: string; reason?: string } | null;
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `Request failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const analystJobs = {
  start: (question: string, sourceId: string, includeReport = false) =>
    request<AnalystJob>('/api/analysis/jobs', { question, source_id: sourceId, include_report: includeReport }),
  get: (jobId: string) =>
    request<AnalystJob>(`/api/analysis/jobs/${encodeURIComponent(jobId)}`),
  review: (jobId: string, approved: boolean) =>
    request<unknown>(`/api/analysis/jobs/${encodeURIComponent(jobId)}/review`, { approved }),
  cancel: (jobId: string) =>
    request<unknown>(`/api/analysis/jobs/${encodeURIComponent(jobId)}/cancel`, {}),
};
