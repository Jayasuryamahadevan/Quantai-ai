/**
 * api/demo.ts — Mock data for demo mode (no backend required).
 * Activated when VITE_DEMO_MODE=true or backend is unreachable.
 */

import type { Source, SourceOverview, HistoryRun, SSEEvent } from './client';

export const DEMO_SOURCES: Source[] = [
  {
    id: 'demo-sales-001',
    name: 'sales_data_2024.csv',
    source_type: 'csv',
    table_name: 'upl_sales_data_2024',
    row_count: 48320,
    col_count: 12,
    created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
  },
  {
    id: 'demo-customers-002',
    name: 'customer_profiles.xlsx',
    source_type: 'excel',
    table_name: 'upl_customer_profiles',
    row_count: 12540,
    col_count: 8,
    created_at: new Date(Date.now() - 86400000 * 5).toISOString(),
  },
];

export const DEMO_OVERVIEW: SourceOverview = {
  source_id: 'demo-sales-001',
  name: 'sales_data_2024.csv',
  row_count: 48320,
  col_count: 12,
  type_breakdown: { float: 4, str: 5, date: 2, int: 1 },
  null_high_columns: ['discount_pct', 'region_code'],
  date_columns: ['order_date', 'ship_date'],
  suggested_questions: [
    'What is the total revenue by product category?',
    'Which region has the highest sales this year?',
    'Show me the top 10 customers by revenue',
    'What is the monthly sales trend?',
    'Which products have the most returns?',
    'How many orders were placed last quarter?',
  ],
};

export const DEMO_PREVIEW_ROWS = Array.from({ length: 20 }, (_, i) => ({
  order_id: `ORD-${2024_000 + i + 1}`,
  product_name: ['Laptop Pro X', 'Wireless Mouse', 'USB-C Hub', 'Monitor 27"', 'Keyboard MX'][i % 5],
  category: ['Electronics', 'Accessories', 'Peripherals'][i % 3],
  quantity: Math.floor(Math.random() * 50) + 1,
  unit_price: +(Math.random() * 500 + 50).toFixed(2),
  revenue: +(Math.random() * 10000 + 500).toFixed(2),
  region: ['North', 'South', 'East', 'West', 'Central'][i % 5],
  order_date: new Date(2024, Math.floor(i / 2), (i % 28) + 1).toISOString().split('T')[0],
  status: ['Completed', 'Shipped', 'Processing', 'Returned'][i % 4],
}));

export const DEMO_HISTORY: HistoryRun[] = [
  {
    id: 'run-001',
    question: 'What is the total revenue by product category?',
    status: 'success',
    confidence: 'High',
    verified: true,
    created_at: new Date(Date.now() - 3600000).toISOString(),
    row_count: 5,
  },
  {
    id: 'run-002',
    question: 'Show me the top 10 customers by order count',
    status: 'success',
    confidence: 'High',
    verified: true,
    created_at: new Date(Date.now() - 7200000).toISOString(),
    row_count: 10,
  },
  {
    id: 'run-003',
    question: 'What was the monthly revenue trend in 2024?',
    status: 'success',
    confidence: 'Medium',
    verified: false,
    created_at: new Date(Date.now() - 86400000).toISOString(),
    row_count: 12,
  },
];

const DEMO_SCENARIOS: Record<string, {
  steps: string[];
  sql: string;
  rows: Record<string, any>[];
  columns: string[];
  chart?: Record<string, any>;
  insight: string;
  confidence: string;
}> = {
  default: {
    steps: ['supervisor', 'source_resolver', 'column_selector', 'query_planner', 'sql_compile', 'validate_execute', 'cross_check', 'cleaner', 'stats_analyzer', 'visualizer', 'insight', 'confidence'],
    sql: 'SELECT category, ROUND(SUM(revenue), 2) AS total_revenue\nFROM `quantai_data`.`upl_sales_data_2024`\nGROUP BY category\nORDER BY total_revenue DESC\nLIMIT 10',
    rows: [
      { category: 'Electronics', total_revenue: 284750.50 },
      { category: 'Peripherals', total_revenue: 156320.25 },
      { category: 'Accessories', total_revenue: 98450.80 },
      { category: 'Software', total_revenue: 67890.00 },
      { category: 'Services', total_revenue: 45230.15 },
    ],
    columns: ['category', 'total_revenue'],
    chart: {
      data: [{
        type: 'bar',
        x: ['Electronics', 'Peripherals', 'Accessories', 'Software', 'Services'],
        y: [284750.50, 156320.25, 98450.80, 67890.00, 45230.15],
        marker: { color: ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'] },
      }],
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8', family: 'Inter' },
        xaxis: { gridcolor: 'rgba(99,102,241,0.1)', title: { text: 'Category' } },
        yaxis: { gridcolor: 'rgba(99,102,241,0.1)', title: { text: 'Total Revenue ($)' }, tickprefix: '$' },
        margin: { t: 20, b: 60, l: 80, r: 20 },
      },
    },
    insight: `**Electronics dominates with $284,750 in revenue** — accounting for **43% of total sales**.\n\nKey findings:\n- 📈 **Electronics** is the top-performing category, nearly double the second-place Peripherals\n- 💡 **Software & Services** combined represent only 17% of revenue, suggesting growth opportunity\n- 🎯 **Top 3 categories** (Electronics, Peripherals, Accessories) contribute **83%** of all revenue\n\n*Recommendation: Consider expanding the Electronics & Peripherals product lines to maximize growth.*`,
    confidence: 'High',
  },
};

function* demoEventGenerator(question: string): Generator<SSEEvent> {
  const scenario = DEMO_SCENARIOS.default;
  const runId = `demo-run-${Date.now()}`;

  yield { type: 'step_started', step: 'supervisor', run_id: runId };

  for (const step of scenario.steps) {
    yield { type: 'step_completed', step, run_id: runId };
  }

  yield {
    type: 'plan',
    plan: { intent: 'aggregate', metric: 'revenue', group_by: ['category'], limit: 10, confidence: 'high' },
    interpretation: `Aggregating total revenue grouped by product category, sorted descending`,
    run_id: runId,
  };

  yield {
    type: 'sql',
    sql: scenario.sql,
    is_fallback: false,
    run_id: runId,
  };

  yield {
    type: 'result_preview',
    rows: scenario.rows,
    columns: scenario.columns,
    total_rows: scenario.rows.length,
    run_id: runId,
  };

  if (scenario.chart) {
    yield {
      type: 'chart',
      chart: scenario.chart,
      chart_type: 'bar',
      run_id: runId,
    };
  }

  yield {
    type: 'verification',
    verified: true,
    details: 'Pandas cross-check passed — SQL and Pandas results match',
    run_id: runId,
  };

  yield {
    type: 'final',
    run_id: runId,
    session_id: 'demo-session',
    question,
    insight: scenario.insight,
    sql: scenario.sql,
    chart: scenario.chart,
    chart_type: 'bar',
    confidence: scenario.confidence,
    verified: true,
    warnings: [],
    trace: scenario.steps.map((s, i) => ({ step: s, status: 'completed', duration_ms: 80 + i * 30 })),
    columns_used: scenario.columns,
    is_fallback_sql: false,
    errors: [],
  };
}

export function streamDemoQuery(
  question: string,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
): () => void {
  let cancelled = false;
  const gen = demoEventGenerator(question);
  const STEP_DELAYS = [200, 150, 300, 600, 400, 800, 500, 200, 400, 600, 700, 200, 100, 100, 100];
  let idx = 0;

  function tick() {
    if (cancelled) return;
    const result = gen.next();
    if (result.done) {
      onDone();
      return;
    }
    onEvent(result.value);
    const delay = STEP_DELAYS[idx++] ?? 150;
    setTimeout(tick, delay);
  }

  // Start with a tiny delay so callers can register handlers
  setTimeout(tick, 50);

  return () => { cancelled = true; };
}

export const isDemoMode = (): boolean =>
  import.meta.env.VITE_DEMO_MODE === 'true' || window.location.search.includes('demo=true');
