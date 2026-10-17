import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Table2 } from 'lucide-react';
import { getAnalytics } from '../lib/api';
import type { AnalyticsData, CategoryAggregate } from '../lib/types';
import { normalizeResolutionPercentages } from '../lib/analytics';
import { EmptyState, ErrorState, PageIntro, Skeleton } from '../components/ui/Primitives';

const categories = ['billing', 'technical', 'refund', 'other'] as const;
const colorTokens: Record<string, string> = { billing: 'var(--accent)', technical: 'var(--chart-technical)', refund: 'var(--warning)', other: 'var(--chart-other)' };
const nice = (name: string) => name.charAt(0).toUpperCase() + name.slice(1);

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeCategories, setActiveCategories] = useState<string[]>([...categories]);
  const [activeSeries, setActiveSeries] = useState({ solved: true, unsolved: true });
  const [percentMode, setPercentMode] = useState(false);
  const [showCategoryTable, setShowCategoryTable] = useState(false);
  const [showRatioTable, setShowRatioTable] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    let active = true; setLoading(true);
    getAnalytics(days).then((result) => { if (active) { setData(result); setError(''); } }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : 'Unable to load analytics.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [days, reloadKey]);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduceMotion(preference.matches);
    update(); preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);

  const categoryData = useMemo(() => (data?.by_category ?? []).filter((row) => activeCategories.includes(row.category)), [data, activeCategories]);
  const ratioData = useMemo(() => (data?.by_category ?? []).filter((row) => activeCategories.includes(row.category)).map((row) => {
    const percentages = normalizeResolutionPercentages(row);
    return {
      ...row,
      solved_value: percentMode ? percentages.solved : row.solved,
      unsolved_value: percentMode ? percentages.unsolved : row.unsolved,
    };
  }), [data, activeCategories, percentMode]);
  const solvedTotal = data?.by_category.reduce((sum, item) => sum + item.solved, 0) ?? 0;
  const resolutionRate = data?.total ? Math.round(solvedTotal / data.total * 100) : 0;
  const toggleCategory = (category: string) => setActiveCategories((current) => current.includes(category) ? current.filter((item) => item !== category) : [...current, category]);

  return <section className="page-content analytics-page">
    <PageIntro eyebrow="Workspace / Insights" title="Analytics" description="A compact read on recent ticket mix and agent resolution outcomes." actions={<div className="range-select" role="group" aria-label="Analytics date range"><button className={days === 7 ? 'is-selected' : ''} aria-pressed={days === 7} onClick={() => setDays(7)}>Last 7 days</button><button className={days === 30 ? 'is-selected' : ''} aria-pressed={days === 30} onClick={() => setDays(30)}>Last 30 days</button></div>} />
    <div className="analytics-summary"><div className="summary-stat"><span>Total tickets</span><strong>{loading ? '—' : data?.total ?? 0}</strong></div><div className="summary-stat"><span>Solved</span><strong>{loading ? '—' : solvedTotal}</strong></div><div className="summary-stat"><span>Resolution rate</span><strong>{loading ? '—' : `${resolutionRate}%`}</strong></div><div className="summary-foot">Last {days} days <span className="demo-dot" /></div></div>
    {error ? <ErrorState message={error} onRetry={() => { setError(''); setReloadKey((value) => value + 1); }} /> : loading ? <div className="analytics-grid"><Skeleton className="chart-skeleton" /><Skeleton className="chart-skeleton" /></div> : !data?.total ? <EmptyState title="No tickets in this range" description="Try Last 30 days to include more sample history." /> : <div className="analytics-grid">
      <article className="panel chart-card">
        <div className="panel-heading"><div><div className="panel-kicker">Volume</div><h2>Category Breakdown</h2><p>Share of recent support conversations</p></div><button className="icon-button" aria-label={showCategoryTable ? 'Show category chart' : 'View category data as table'} onClick={() => setShowCategoryTable((value) => !value)}><Table2 size={16} /></button></div>
        {showCategoryTable ? <div className="chart-table-scroll"><table className="chart-data-table"><caption className="visually-hidden">Ticket totals by category for the last {days} days</caption><thead><tr><th>Category</th><th>Tickets</th><th>Share</th></tr></thead><tbody>{data.by_category.map((row) => <tr key={row.category}><th scope="row">{nice(row.category)}</th><td>{row.total}</td><td>{data.total ? `${Math.round(row.total / data.total * 100)}%` : '0%'}</td></tr>)}</tbody></table></div> : <>
          <div className="donut-layout"><div className="donut-wrap" role="img" aria-label={`Category breakdown for ${data.total} tickets`}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={categoryData} dataKey="total" nameKey="category" innerRadius={72} outerRadius={103} paddingAngle={4} stroke="none" isAnimationActive={!reduceMotion} onClick={(slice) => toggleCategory(String(slice.category))}>{categoryData.map((entry) => <Cell key={entry.category} fill={colorTokens[entry.category]} />)}</Pie><Tooltip content={<CategoryTooltip total={data.total} />} /></PieChart></ResponsiveContainer><div className="donut-center"><strong>{data.total}</strong><span>tickets</span></div></div><div className="category-legend">{data.by_category.map((row) => <button key={row.category} className={`legend-row ${activeCategories.includes(row.category) ? '' : 'is-muted'}`} aria-pressed={activeCategories.includes(row.category)} onClick={() => toggleCategory(row.category)}><span className="legend-swatch" style={{ background: colorTokens[row.category] }} /><span className="legend-name">{nice(row.category)}</span><strong>{row.total}</strong><small>{data.total ? Math.round(row.total / data.total * 100) : 0}%</small></button>)}</div></div>
        </>}
        <div className="chart-card-footer"><span>Ticket category from the support queue</span><button className="text-button" onClick={() => setShowCategoryTable((value) => !value)}>{showCategoryTable ? 'Back to chart' : 'View as table'} <Table2 size={13} /></button></div>
      </article>

      <article className="panel chart-card">
        <div className="panel-heading"><div><div className="panel-kicker">Outcomes</div><h2>Resolution Ratio</h2><p>Resolved vs. unresolved by category</p></div><button className="icon-button" aria-label={showRatioTable ? 'Show resolution chart' : 'View resolution data as table'} onClick={() => setShowRatioTable((value) => !value)}><Table2 size={16} /></button></div>
        {!showRatioTable && <div className="chart-controls"><div className="segmented-control" role="group" aria-label="Resolution values"><button className={!percentMode ? 'is-selected' : ''} aria-pressed={!percentMode} onClick={() => setPercentMode(false)}>Count</button><button className={percentMode ? 'is-selected' : ''} aria-pressed={percentMode} onClick={() => setPercentMode(true)}>Percent</button></div><div className="chart-legend"><button className={!activeSeries.solved ? 'is-muted' : ''} aria-pressed={activeSeries.solved} onClick={() => setActiveSeries((value) => ({ ...value, solved: !value.solved }))}><span className="legend-swatch solved-swatch" />Solved</button><button className={!activeSeries.unsolved ? 'is-muted' : ''} aria-pressed={activeSeries.unsolved} onClick={() => setActiveSeries((value) => ({ ...value, unsolved: !value.unsolved }))}><span className="legend-swatch unsolved-swatch" />Unsolved</button></div></div>}
        {showRatioTable ? <div className="chart-table-scroll"><table className="chart-data-table"><caption className="visually-hidden">Ticket resolution by category</caption><thead><tr><th>Category</th><th>Solved</th><th>Unsolved</th><th>Total</th><th>Solved %</th></tr></thead><tbody>{data.by_category.map((row) => <tr key={row.category}><th scope="row">{nice(row.category)}</th><td>{row.solved}</td><td>{row.unsolved}</td><td>{row.total}</td><td>{row.total ? `${Math.round(row.solved / row.total * 100)}%` : '0%'}</td></tr>)}</tbody></table></div> : <div className="bar-chart-wrap" role="img" aria-label={`Resolution ratio by category for the last ${days} days`}><ResponsiveContainer width="100%" height="100%"><BarChart data={ratioData} margin={{ top: 8, right: 8, left: -18, bottom: 4 }} barGap={4}><CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="category" tickFormatter={nice} axisLine={false} tickLine={false} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} /><YAxis domain={percentMode ? [0, 100] : [0, 'auto']} tickFormatter={(value) => percentMode ? `${value}%` : String(value)} axisLine={false} tickLine={false} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} /><Tooltip content={<ResolutionTooltip percent={percentMode} />} />{activeSeries.solved && <Bar dataKey="solved_value" name="Solved" stackId="resolution" fill="var(--success)" radius={[0, 0, 0, 0]} isAnimationActive={!reduceMotion} />}{activeSeries.unsolved && <Bar dataKey="unsolved_value" name="Unsolved" stackId="resolution" fill="var(--chart-other)" radius={[5, 5, 0, 0]} isAnimationActive={!reduceMotion} />}</BarChart></ResponsiveContainer></div>}
        <div className="chart-card-footer"><span>{percentMode && !showRatioTable ? 'Each category normalized to 100%' : 'Ticket counts in the selected range'}</span><button className="text-button" onClick={() => setShowRatioTable((value) => !value)}>{showRatioTable ? 'Back to chart' : 'View as table'} <Table2 size={13} /></button></div>
      </article>
    </div>}
  </section>;
}

function CategoryTooltip({ active, payload, total }: { active?: boolean; payload?: Array<{ payload: CategoryAggregate }>; total: number }) {
  if (!active || !payload?.[0]) return null;
  const row = payload[0].payload;
  return <div className="chart-tooltip"><strong>{nice(row.category)}</strong><span>{row.total} tickets · {total ? Math.round(row.total / total * 100) : 0}%</span></div>;
}
function ResolutionTooltip({ active, payload, percent }: { active?: boolean; payload?: Array<{ payload: CategoryAggregate & { solved_value: number; unsolved_value: number } }>; percent: boolean }) {
  if (!active || !payload?.[0]) return null;
  const row = payload[0].payload;
  const solvedPercent = percent ? row.solved_value : row.total ? Math.round(row.solved / row.total * 100) : 0;
  const unsolvedPercent = percent ? row.unsolved_value : row.total ? 100 - solvedPercent : 0;
  return <div className="chart-tooltip"><strong>{nice(row.category)}</strong><span>Solved: {row.solved}{percent ? ` (${solvedPercent}%)` : ''}</span><span>Unsolved: {row.unsolved}{percent ? ` (${unsolvedPercent}%)` : ''}</span><span>Total: {row.total} · Solved {solvedPercent}%</span></div>;
}
