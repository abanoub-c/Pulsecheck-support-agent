import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, CircleCheck, CircleX, Clock3, Wrench } from 'lucide-react';
import type { ThreadState, ToolCall, TraceStep } from '../../lib/types';

const stateLabels: Array<[keyof ThreadState, string]> = [
  ['category', 'Category'], ['pending_categories', 'Pending categories'], ['confidence', 'Confidence'],
  ['clarify_attempts', 'Clarify attempts'], ['turn_count', 'Turn count'], ['resolution_status', 'Resolution status'], ['escalation_reason', 'Escalation reason'],
];
function stringify(value: unknown) {
  try { return JSON.stringify(value, null, 2); }
  catch { return String(value); }
}
function derivedToolCalls(steps: TraceStep[]): ToolCall[] {
  const tools = new Map<string, ToolCall>();
  for (const step of steps) {
    const detail = typeof step.detail === 'object' && step.detail ? step.detail as Record<string, unknown> : {};
    const tool = typeof detail.tool === 'string' ? detail.tool : '';
    if (!tool) continue;
    if (step.kind === 'tool_call') {
      const args = (detail.args && typeof detail.args === 'object' ? detail.args : {}) as Record<string, unknown>;
      tools.set(tool, { id: step.id, tool, args, result: null, ok: true, duration_ms: 0 });
    } else if (step.kind === 'tool_result') {
      const previous = tools.get(tool) ?? { id: step.id, tool, args: {}, result: null, ok: true, duration_ms: 0 };
      tools.set(tool, { ...previous, result: detail.result ?? detail, ok: detail.ok !== false });
    }
  }
  return [...tools.values()];
}

export function ThinkingTrace({ id, steps, tools: suppliedTools = [], state, startedAt, finishedAt, streaming = false }: {
  id: string; steps: TraceStep[]; tools?: ToolCall[]; state: ThreadState | null; startedAt?: string; finishedAt?: string; streaming?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const tools = suppliedTools.length ? suppliedTools : derivedToolCalls(steps);
  const duration = startedAt && finishedAt ? Math.max(0, Math.round((new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000)) : null;
  const label = useMemo(() => {
    if (streaming) return 'Thinking…';
    if (duration === null) return 'View execution steps & tools';
    return duration < 1 ? 'Thought for under a second' : `Thought for ${duration} second${duration === 1 ? '' : 's'}`;
  }, [streaming, duration]);

  return <div className={`thinking-trace ${streaming ? 'is-streaming' : ''}`}>
    <button className="thinking-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen((value) => !value)}>
      {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      <span>{label}</span>
      {!streaming && <span className="trace-count">{steps.length} steps{tools.length ? ` · ${tools.length} tools` : ''}</span>}
      {streaming && <span className="trace-live-dot" aria-hidden="true" />}
    </button>
    {open && <div id={id} className="trace-panel">
      <section className="trace-group"><h4>Steps</h4>
        {steps.length ? <ol className="trace-timeline">{steps.map((step, index) => <li key={step.id} className={index === steps.length - 1 && streaming ? 'is-latest' : ''}>
          <span className="timeline-marker">{index + 1}</span><div className="timeline-copy"><div className="timeline-meta"><span>{step.node.replaceAll('_', ' ')}</span><time>{new Date(step.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time></div><strong>{step.title}</strong><p>{typeof step.detail === 'string' ? step.detail : stringify(step.detail)}</p></div>
        </li>)}</ol> : <p className="trace-empty">Steps will appear as the agent works.</p>}
      </section>
      <section className="trace-group"><h4>Tool calls</h4>
        {tools.length ? <div className="tool-list">{tools.map((tool) => <article className="tool-card" key={tool.id}>
          <div className="tool-card-head"><span className="tool-icon"><Wrench size={13} /></span><code>{tool.tool}</code>{tool.ok ? <CircleCheck className="tool-ok" size={14} aria-label="Succeeded" /> : <CircleX className="tool-failed" size={14} aria-label="Failed" />}{tool.duration_ms > 0 && <span className="tool-duration"><Clock3 size={11} /> {tool.duration_ms}ms</span>}</div>
          <details><summary>Arguments</summary><pre>{stringify(tool.args)}</pre></details>
          {tool.result !== null && <details><summary>Result</summary><pre>{stringify(tool.result).slice(0, 1200)}</pre></details>}
        </article>)}</div> : <p className="trace-empty">No tools used for this response.</p>}
      </section>
      <section className="trace-group"><h4>State</h4>
        {state ? <dl className="trace-state">{stateLabels.map(([key, labelText]) => <div key={key}><dt>{labelText}</dt><dd>{Array.isArray(state[key]) ? (state[key] as string[]).join(', ') || '—' : state[key] === null || state[key] === '' ? '—' : key === 'confidence' ? `${Math.round(Number(state[key]) * 100)}%` : String(state[key])}</dd></div>)}</dl> : <p className="trace-empty">State snapshot will appear when available.</p>}
      </section>
    </div>}
  </div>;
}
