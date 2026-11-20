import { createElement, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, Clock3, Database, Info, Users, UserPlus } from 'lucide-react';

function numeric(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  const result = Number(value);
  return Number.isFinite(result) && result >= 0 ? result : null;
}
const axisCount = value => value < 10000 ? new Intl.NumberFormat('en-IN').format(value) : new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
const count = value => numeric(value) === null ? 'Unavailable' : new Intl.NumberFormat('en-IN').format(Number(value));
function money(row) {
  const value = numeric(row.estimated_amount);
  if (value === null) return 'Unavailable';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: row.currency, currencyDisplay: 'code', minimumFractionDigits: 2, maximumFractionDigits: value > 0 && value < .01 ? 6 : 2 }).format(value);
}
function day(value) {
  const parsed = new Date(String(value).slice(0, 10) + 'T00:00:00Z');
  return Number.isNaN(parsed.getTime()) ? 'Unknown date' : new Intl.DateTimeFormat('en-IN', { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(parsed);
}
function date(value, zone = 'UTC') {
  const parsed = new Date(value);
  return !value || Number.isNaN(parsed.getTime()) ? 'Unavailable' : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: zone }).format(parsed);
}
function Empty({ children }) {
  return <div className="ao-empty"><BarChart3 size={28} strokeWidth={1.5} aria-hidden="true" /><p>{children}</p></div>;
}
function Metric({ icon: Icon, label, value, children }) {
  return <article className="ao-metric"><div className="ao-metric-label">{createElement(Icon, { size: 20, strokeWidth: 1.7, 'aria-hidden': true })}<h2>{label}</h2></div><p className="ao-metric-value" aria-label={value === 'Unavailable' ? 'Unavailable' : undefined}>{value === 'Unavailable' ? '\u2014' : value}</p><div className="ao-metric-note">{children}</div></article>;
}
function SectionInfo({ label, children }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const tooltip = useRef(null);
  useLayoutEffect(() => {
    if (!open || above) return;
    const bounds = tooltip.current.getBoundingClientRect();
    const heading = tooltip.current.closest('.ao-title-line').getBoundingClientRect();
    if (bounds.bottom > window.innerHeight && heading.top > bounds.height + 8) setAbove(true);
  }, [open, above]);
  function show() { setAbove(false); setOpen(true); }
  return <span className="ao-info" onMouseEnter={show} onMouseLeave={() => setOpen(false)} onFocus={show} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); } }}>
    <button type="button" className="ao-info-button" aria-label={`About ${label}`} aria-describedby={id} onClick={show}><Info size={16} strokeWidth={1.7} aria-hidden="true" /></button>
    <span ref={tooltip} id={id} role="tooltip" className="ao-info-tooltip" data-above={above || undefined} hidden={!open}>{children}</span>
  </span>;
}
function useChartWidth() {
  const [node, setNode] = useState(null);
  const [width, setWidth] = useState(680);
  useEffect(() => {
    if (!node) return;
    const measure = () => setWidth(Math.max(240, Math.round(node.getBoundingClientRect().width)));
    measure();
    const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, width];
}
function Growth({ days }) {
  const [kind, setKind] = useState('total_users');
  const [frame, width] = useChartWidth();
  const left = 46, right = width - 16, span = right - left;
  const [focused, setFocused] = useState(null);
  const id = useId();
  const observations = days.filter(item => numeric(item[kind]) !== null);
  const max = Math.max(4, ...observations.map(item => Number(item[kind])));
  const magnitude = 10 ** Math.floor(Math.log10(max / 4));
  const step = Math.ceil(max / 4 / magnitude) * magnitude;
  const ceiling = step * 4;
  const points = days.map((item, index) => numeric(item[kind]) === null ? null : ({
    x: days.length === 1 ? (left + right) / 2 : left + index * span / (days.length - 1),
    y: 132 - Number(item[kind]) / ceiling * 120, item,
  }));
  // Missing days break the line; unknown history never becomes zero observations.
  const segments = [];
  points.forEach((point, index) => {
    if (!point) return;
    const previous = points[index - 1];
    if (!previous || Date.parse(point.item.day_bucket) - Date.parse(previous.item.day_bucket) > 86400000) segments.push([]);
    segments[segments.length - 1].push(point);
  });
  const ticks = [...new Set([0, Math.floor((days.length - 1) / 3), Math.floor((days.length - 1) * 2 / 3), days.length - 1])].filter(i => i >= 0);
  return <article className="ao-panel ao-growth"><div className="ao-panel-heading"><div><h2>User growth</h2><p>Verified users within observed history</p></div><div className="ao-segments" role="group" aria-label="Growth metric"><button aria-pressed={kind === 'total_users'} onClick={() => { setKind('total_users'); setFocused(null); }}>Total users</button><button aria-pressed={kind === 'new_users'} onClick={() => { setKind('new_users'); setFocused(null); }}>New users</button></div></div>
    {observations.length ? <figure ref={frame}><svg className="ao-growth-chart" viewBox={`0 0 ${width} 160`} role="img" aria-label={`${kind === 'total_users' ? 'Total' : 'New'} verified users by observed day. Exact values follow in the data table.`}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1671ed" stopOpacity=".18" /><stop offset="1" stopColor="#1671ed" stopOpacity=".02" /></linearGradient></defs>
      {[0, 1, 2, 3, 4].map(i => <g key={i}><line x1={left} x2={right} y1={132 - i * 30} y2={132 - i * 30} className="ao-grid-line" /><text x="36" y={136 - i * 30} textAnchor="end">{axisCount(step * i)}</text></g>)}
      {segments.filter(segment => segment.length > 1).map((segment, index) => <g key={index}><polygon points={`${segment[0].x},132 ${segment.map(p => `${p.x},${p.y}`).join(' ')} ${segment[segment.length - 1].x},132`} fill={`url(#${id})`} /><polyline points={segment.map(p => `${p.x},${p.y}`).join(' ')} className="ao-growth-line" /></g>)}
      {ticks.map(index => <text key={index} x={points[index]?.x ?? (days.length === 1 ? (left + right) / 2 : left + index * span / (days.length - 1))} y="154" textAnchor="middle">{day(days[index].day_bucket)}</text>)}
      {points.filter(Boolean).map(point => <circle key={point.item.day_bucket} cx={point.x} cy={point.y} r="4.5" className="ao-chart-point" tabIndex={0} role="img" aria-label={`${day(point.item.day_bucket)}: ${count(point.item[kind])} ${kind === 'total_users' ? 'total' : 'new'} verified users`} onMouseEnter={() => setFocused(point.item)} onMouseLeave={() => setFocused(null)} onFocus={() => setFocused(point.item)} onBlur={() => setFocused(null)}><title>{day(point.item.day_bucket)}: {count(point.item[kind])} verified users</title></circle>)}
    </svg><figcaption aria-live="polite">{focused ? `${day(focused.day_bucket)}: ${count(focused[kind])} verified users` : observations.length === 1 ? 'One observed day. Earlier history is unavailable.' : 'Observed daily values'}</figcaption></figure> : <Empty>No verified user observations are available for this window.</Empty>}

  </article>;
}
function Models({ models }) {
  const sorted = [...models].sort((a, b) => Number(b.attempts) - Number(a.attempts));
  const total = sorted.reduce((sum, item) => sum + (numeric(item.attempts) ?? 0), 0);
  return <article className="ao-panel ao-models"><div className="ao-panel-heading"><div><h2>Most used models</h2><p>Actual executed attempts</p></div></div>{total > 0 ? <ol className="ao-ranking">{sorted.map((item, index) => <li key={item.provider + item.model} title={`${item.provider} / ${count(item.attempts)} attempts`} tabIndex={0} aria-label={`${item.provider}, ${item.model}: ${count(item.attempts)} attempts, ${(Number(item.attempts) / total * 100).toFixed(1)} percent of observed attempts`}><span className="ao-rank">{index + 1}</span><div className="ao-rank-content"><strong title={item.model}>{item.model}</strong><div className="ao-rank-baseline"><span className="ao-provider-label">{item.provider}</span><div className="ao-track" aria-hidden="true"><span style={{ width: `${Number(item.attempts) / total * 100}%` }} /></div></div></div><span className="ao-share">{Math.round(Number(item.attempts) / total * 100)}%</span></li>)}</ol> : <Empty>No executed model attempts observed. Model selection is not usage.</Empty>}</article>;
}
function Attempts({ models }) {
  const [frame, width] = useChartWidth();
  const valid = models.filter(item => numeric(item.attempts) !== null && numeric(item.completed) !== null);
  const ceiling = Math.max(4, ...valid.map(item => Number(item.attempts)));
  const step = Math.ceil(ceiling / 4);
  const [focused, setFocused] = useState('');
  return <article className="ao-panel ao-activity"><div className="ao-panel-heading"><div><div className="ao-title-line"><h2>Activity</h2><SectionInfo label="Activity">Observed AI model attempts in the selected period. Compare total attempts with completed attempts; totals also include failures and interrupted streams.</SectionInfo></div><p>Executed attempts by model in this window</p></div><div className="ao-legend"><span><i />Total attempts</span><span><i />Completed</span></div></div>{valid.length ? <figure ref={frame}><svg viewBox={`0 0 ${width} 160`} role="img" aria-label="Executed and completed attempts by model. Exact values follow in the data table.">
    {[0, 1, 2, 3, 4].map(i => <g key={i}><line x1="44" x2={width - 12} y1={125 - i * 28} y2={125 - i * 28} className="ao-grid-line" /><text x="34" y={129 - i * 28} textAnchor="end">{axisCount(step * i)}</text></g>)}
    {valid.map((item, index) => { const slot = (width - 60) / valid.length; const x = 46 + index * slot; const bar = Math.min(36, slot * .34); return <g key={item.provider + item.model} tabIndex={0} role="img" aria-label={`${item.model}: ${count(item.attempts)} total attempts, ${count(item.completed)} completed`} onFocus={() => setFocused(`${item.model}: ${count(item.attempts)} attempts, ${count(item.completed)} completed`)} onBlur={() => setFocused('')} onMouseEnter={() => setFocused(`${item.model}: ${count(item.attempts)} attempts, ${count(item.completed)} completed`)} onMouseLeave={() => setFocused('')}><title>{item.provider} / {item.model}: {count(item.attempts)} attempts, {count(item.completed)} completed</title><rect x={x + slot / 2 - bar - 2} y={125 - Number(item.attempts) / (step * 4) * 112} width={bar} height={Number(item.attempts) / (step * 4) * 112} rx="4" fill="#1671ed" /><rect x={x + slot / 2 + 2} y={125 - Number(item.completed) / (step * 4) * 112} width={bar} height={Number(item.completed) / (step * 4) * 112} rx="4" fill="#00877e" /><text x={x + slot / 2} y="150" textAnchor="middle">{valid.length <= 4 && width > 500 ? item.model.length > 15 ? item.model.slice(0, 12) + '...' : item.model : index + 1}</text></g>; })}
  </svg><figcaption aria-live="polite">{focused || 'Full model details in Data coverage'}</figcaption></figure> : <Empty>No observed attempts to chart. Historical activity is unavailable before instrumentation.</Empty>}


  </article>;
}
function Costs({ costs, unknown }) {
  const covered = costs.reduce((sum, row) => sum + (numeric(row.covered_attempts) ?? 0), 0);
  const total = numeric(unknown) === null ? null : covered + Number(unknown);
  return <article className="ao-panel ao-costs"><div className="ao-panel-heading"><div><div className="ao-title-line"><h2>API cost breakdown</h2><SectionInfo label="API cost breakdown">Estimated spending from measured token usage and configured rates, grouped by currency. Missing usage or rates are excluded; this is not a provider invoice.</SectionInfo></div><p>Estimates by currency</p></div></div>{costs.length ? <ul className="ao-cost-list">{costs.map(row => <li key={row.currency}><Database size={20} strokeWidth={1.5} aria-hidden="true" /><div><strong>{row.currency}</strong><span>{count(row.covered_attempts)} covered attempts</span></div><strong>{money(row)}</strong></li>)}</ul> : <Empty>No covered estimate is available. Unknown usage or rates are not zero cost.</Empty>}
    <div className="ao-cost-coverage"><div><strong>Measured cost coverage</strong><span>{total > 0 ? `${Math.round(covered / total * 100)}% of observed attempts` : 'Unavailable'}</span></div>{total > 0 && <div className="ao-coverage-track" role="img" aria-label={`${covered} cost-covered attempts, ${unknown} unknown-cost attempts`}><span style={{ width: `${covered / total * 100}%` }} /></div>}<p>{count(unknown)} unknown-cost attempts. Provider-confirmed charges and provider-level cost breakdown are unavailable.</p></div>
  </article>;
}
export default function AdminOverview({ data, status = 'ready' }) {
  const [, updateAge] = useState(0);
  useEffect(() => {
    const remaining = Date.parse(data?.as_of) + 300001 - Date.now();
    if (remaining > 0) { const timer = setTimeout(() => updateAge(value => value + 1), remaining); return () => clearTimeout(timer); }
  }, [data?.as_of]);
  if (status !== 'ready' || !data) return <section className="admin-overview" aria-label="Operational overview" aria-busy={status === 'loading'}><div className="ao-state" role={status === 'loading' ? 'status' : 'alert'}>{status === 'loading' ? 'Loading authorized metrics...' : 'Metrics are unavailable. No missing values are shown as zero.'}</div><div className="ao-metrics">{['Verified users', 'New verified users', 'Active users', 'Estimated API cost'].map(label => <article className="ao-metric" key={label}><h2>{label}</h2><>{status === 'loading' ? <span className="ao-skeleton" /> : <p className="ao-metric-value" aria-label="Unavailable">{'\u2014'}</p>}<p>{status === 'loading' ? 'Awaiting authorized data' : 'No authorized snapshot'}</p></></article>)}</div><div className="ao-primary-grid"><article className="ao-panel"><h2>User growth</h2><Empty>{status === 'loading' ? 'Loading observations' : 'Observations unavailable'}</Empty></article><article className="ao-panel"><h2>Most used models</h2><Empty>{status === 'loading' ? 'Loading observed usage' : 'Usage unavailable'}</Empty></article></div><div className="ao-secondary-grid">{['Activity','API cost breakdown'].map(title => <article className="ao-panel" key={title}><h2>{title}</h2><Empty>{status === 'loading' ? 'Loading authorized data' : 'Data unavailable'}</Empty></article>)}</div></section>;
  const days = data.daily_registrations || [], models = data.models || [], costs = data.costs || [];
  const covered = costs.reduce((sum, row) => sum + (numeric(row.covered_attempts) ?? 0), 0);
  const unknown = numeric(data.cost_unknown_attempts);
  const observed = unknown === null ? null : unknown + covered;
  const growth = data.growth_percent === null || data.growth_percent === undefined ? null : Number(data.growth_percent);
  return <section className="admin-overview" aria-label="Operational overview">
    <div className="ao-metrics"><Metric icon={Users} label="Verified current users" value={count(data.total_users)}>{Number.isFinite(growth) ? <span>{growth < 0 ? <ArrowDownRight size={14} aria-hidden="true" /> : <ArrowUpRight size={14} aria-hidden="true" />}{growth}% growth in selected window</span> : 'Earlier growth history unavailable'}</Metric><Metric icon={UserPlus} label="New verified users" value={count(data.new_users)}>{data.new_users === null ? 'Window predates observed history' : 'Within selected date range'}</Metric><Metric icon={Activity} label="Active users" value={count(data.active_7_days)}>Distinct qualifying activity / 7 days</Metric><Metric icon={Database} label="Estimated API cost" value={costs.length === 1 ? money(costs[0]) : costs.length > 1 ? 'Multiple currencies' : 'Unavailable'}>{observed > 0 ? `${unknown > 0 ? 'Partial estimate' : 'Estimate'} / ${Math.round(covered / observed * 100)}% coverage` : 'No covered cost estimate'}</Metric></div>
    <div className="ao-primary-grid"><Growth days={days} /><Models models={models} /></div>
    <div className="ao-secondary-grid"><Attempts models={models} /><Costs costs={costs} unknown={data.cost_unknown_attempts} /></div>
    <footer className="ao-footer">{Date.now() - Date.parse(data.as_of) > 300000 && <span className="ao-stale">Older snapshot. Refresh for current data.</span>}<span><Clock3 size={16} aria-hidden="true" />Updated {date(data.as_of, data.timezone)}</span><span>30-day active: {count(data.active_30_days)} / last 5-min activity: {count(data.current_activity_5_minutes)} (approx.)</span><details className="ao-definitions"><summary><Info size={16} aria-hidden="true" />Metric definitions / Data coverage</summary><div><p>Window: {date(data.start, data.timezone)} up to {date(data.end, data.timezone)} ({data.timezone}). No prior-period comparison is inferred.</p><p>Registration source: {String(data.registration_coverage || 'unavailable').replaceAll('_', ' ')}. Deleted historical accounts before observation are unavailable.</p><p>Activity is successful session starts or settled product operations, not login, polling or online presence. Coverage: {String(data.activity_coverage || 'unavailable').replaceAll('_', ' ')}, from {date(data.coverage_started_at, data.timezone)}.</p><p>Model usage counts observed provider attempts, including failed and aborted requests; selection alone is excluded. {String(data.attempt_coverage || 'unavailable').replaceAll('_', ' ')}. SDK-internal retries may not be individually observable.</p><p>Estimates require measured tokens and a versioned rate valid at execution. Currency is preserved; no exchange rate or provider invoice is inferred.</p><p>Metadata only. Private customer content is unavailable to both administration roles. Completed attempts are a subset of total attempts; failures and aborted streams remain in totals.</p>    <details className="ao-data"><summary>View user data</summary><div className="ac-table" role="region" aria-label="Daily verified user counts" tabIndex={0}><table><thead><tr><th>Day</th><th>Total verified users</th><th>New verified users</th></tr></thead><tbody>{days.map(item => <tr key={item.day_bucket}><td>{day(item.day_bucket)}</td><td>{count(item.total_users)}</td><td>{count(item.new_users)}</td></tr>)}</tbody></table></div></details>    <details className="ao-data"><summary>View executed model data</summary><div className="ac-table" role="region" aria-label="Executed model attempts" tabIndex={0}><table><thead><tr>{['Provider', 'Model', 'Attempts', 'Completed', 'Failed', 'Aborted', 'Token coverage'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{models.map(item => <tr key={item.provider + item.model}>{['provider', 'model', 'attempts', 'completed', 'failed', 'aborted', 'token_covered'].map(key => <td key={key}>{['provider', 'model'].includes(key) ? item[key] : count(item[key])}</td>)}</tr>)}</tbody></table></div></details></div></details></footer>
  </section>;
}
