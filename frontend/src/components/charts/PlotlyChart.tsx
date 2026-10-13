import React from 'react';
import { useAppStore } from '../../store/useAppStore';

interface Props {
  chart: Record<string, any>;
  height?: number;
}

// Load the pre-minified distribution only when a result includes a chart.
const Plot = React.lazy(async () => {
  const [{ default: createPlotlyComponent }, { default: Plotly }] = await Promise.all([
    import('react-plotly.js/factory'),
    import('plotly.js-dist-min'),
  ]);
  return { default: createPlotlyComponent(Plotly) };
});

const DARK_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#94a3b8', family: 'Inter, sans-serif', size: 12 },
  margin: { t: 20, b: 50, l: 60, r: 20, pad: 4 },
  legend: { bgcolor: 'rgba(13,13,31,0.8)', bordercolor: 'rgba(99,102,241,0.2)', borderwidth: 1 },
  xaxis: {
    gridcolor: 'rgba(99,102,241,0.08)',
    linecolor: 'rgba(99,102,241,0.15)',
    tickcolor: 'rgba(99,102,241,0.2)',
    zerolinecolor: 'rgba(99,102,241,0.15)',
  },
  yaxis: {
    gridcolor: 'rgba(99,102,241,0.08)',
    linecolor: 'rgba(99,102,241,0.15)',
    tickcolor: 'rgba(99,102,241,0.2)',
    zerolinecolor: 'rgba(99,102,241,0.15)',
  },
};

// QuantAI brand color palette for traces
const BRAND_COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#c084fc', '#e879f9',
  '#22d3ee', '#34d399', '#fbbf24', '#f87171', '#60a5fa',
];

function applyBrandColors(data: any[]): any[] {
  return data.map((trace, i) => {
    const color = BRAND_COLORS[i % BRAND_COLORS.length];
    const patch: any = {};

    if (trace.type === 'bar' && !trace.marker?.color) {
      patch.marker = { ...(trace.marker || {}), color };
    }
    if (trace.type === 'scatter' && !trace.line?.color) {
      patch.line = { ...(trace.line || {}), color, width: 2.5 };
      patch.marker = { ...(trace.marker || {}), color, size: 6 };
    }
    if (trace.type === 'pie' && !trace.marker?.colors) {
      patch.marker = { ...(trace.marker || {}), colors: BRAND_COLORS };
    }

    return { ...trace, ...patch };
  });
}

export const PlotlyChart: React.FC<Props> = ({ chart, height = 380 }) => {
  const theme = useAppStore((state) => state.theme);
  const lightTheme = theme === 'light';
  const data = applyBrandColors(chart.data || []);
  // Chart payloads may contain a width chosen by the backend or Plotly's
  // defaults. Let the available chat column determine width so charts resize
  // cleanly instead of keeping a narrow or stale initial size.
  const sourceLayout = { ...(chart.layout || {}) };
  delete sourceLayout.width;
  const themedAxis = (name: 'xaxis' | 'yaxis') => {
    const sourceAxis = chart.layout?.[name] || {};
    return {
      ...DARK_LAYOUT[name],
      ...sourceAxis,
      ...(lightTheme ? {
        gridcolor: 'rgba(148,163,184,0.24)',
        linecolor: 'rgba(100,116,139,0.36)',
        tickcolor: 'rgba(100,116,139,0.36)',
        zerolinecolor: 'rgba(100,116,139,0.3)',
        tickfont: { ...(sourceAxis.tickfont || {}), color: '#475569' },
        title: {
          ...(sourceAxis.title || {}),
          font: { ...(sourceAxis.title?.font || {}), color: '#334155' },
        },
      } : {}),
    };
  };
  const layout = {
    ...DARK_LAYOUT,
    ...sourceLayout,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {
      ...DARK_LAYOUT.font,
      ...(chart.layout?.font || {}),
      ...(lightTheme ? { color: '#475569' } : {}),
    },
    legend: lightTheme
      ? { ...DARK_LAYOUT.legend, ...(chart.layout?.legend || {}), bgcolor: 'rgba(255,255,255,0.9)', bordercolor: 'rgba(148,163,184,0.35)' }
      : { ...DARK_LAYOUT.legend, ...(chart.layout?.legend || {}) },
    xaxis: themedAxis('xaxis'),
    yaxis: themedAxis('yaxis'),
    autosize: true,
    height,
  };

  const config = {
    displayModeBar: true,
    modeBarButtonsToRemove: ['sendDataToCloud', 'toImage'] as any,
    displaylogo: false,
    responsive: true,
    toImageButtonOptions: { format: 'png' as const, scale: 2 },
  };

  return (
    <React.Suspense
      fallback={
        <div className="h-[380px] shimmer rounded-xl" />
      }
    >
      <div className="w-full min-w-0" style={{ height }}>
        <Plot
          data={data}
          layout={layout}
          config={config}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler
        />
      </div>
    </React.Suspense>
  );
};
