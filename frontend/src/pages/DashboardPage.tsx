import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowUpRight, BadgeCheck, Clock3, FileText, LoaderCircle, RefreshCw, ShieldAlert, X } from 'lucide-react';
import { decideEscalation, getCustomerDetail, getDashboardSummary, getEscalations } from '../lib/api';
import { useApp } from '../lib/AppContext';
import type { CustomerDetail, DashboardSummary, Escalation } from '../lib/types';
import { Button, EmptyState, ErrorState, PageIntro, Skeleton, StatusChip } from '../components/ui/Primitives';
import { ThemedSelect } from '../components/ui/ThemedSelect';

const reasonLabels: Record<string, string> = {
  refund_exceeds_threshold: 'Refund over threshold',
  refund_requires_review: 'Refund requires review',
  loop_guard_exceeded: 'Loop limit reached',
  tool_call_failed: 'Tool call failed',
  customer_requested_human: 'Customer requested a human',
  low_confidence: 'Low confidence',
  clarification_exhausted: 'Clarification exhausted',
  uncategorized_request: 'Uncategorized request',
};
function reasonTone(reason: string): 'warning' | 'danger' | 'info' | 'neutral' {
  if (reason === 'refund_exceeds_threshold') return 'warning';
  if (reason === 'loop_guard_exceeded' || reason === 'tool_call_failed') return 'danger';
  if (reason === 'customer_requested_human') return 'info';
  return 'neutral';
}
function elapsedLabel(value: string) {
  // Legacy seeded CRM rows only have a date. Don't invent an hour-level age
  // from midnight; show the date-level age until an exact timestamp exists.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    const createdDate = new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.max(0, Math.floor((today.getTime() - createdDate.getTime()) / 86400000));
    return days === 0 ? 'Today' : `${days}d`;
  }

  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return '—';
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
function reasonCode(item: Escalation) { return item.reason_code ?? item.reasoning.split(' — ', 1)[0]; }

export default function DashboardPage() {
  const [items, setItems] = useState<Escalation[]>([]);
  const [status, setStatus] = useState<'pending' | 'resolved'>('pending');
  const [reason, setReason] = useState('All reasons');
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectNote, setRejectNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [openIncidents, setOpenIncidents] = useState(0);
  const [customerDetail, setCustomerDetail] = useState<CustomerDetail | null>(null);
  const [customerDetailError, setCustomerDetailError] = useState('');
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const { notify, setSelectedCustomerId } = useApp();
  const navigate = useNavigate();

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    try {
      const [data, dashboardSummary] = await Promise.all([getEscalations(status), getDashboardSummary()]);
      setItems(data.items);
      setSummary(dashboardSummary);
      setOpenIncidents(dashboardSummary.open_incidents ?? 0);
      setError('');
      setSelectedId((current) => data.items.some((item) => item.escalation_id === current) ? current : data.items[0]?.escalation_id ?? '');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to load the escalation queue.');
    } finally { if (initial) setLoading(false); }
  }, [status]);

  useEffect(() => {
    void load(true);
    const refreshWhenVisible = () => { if (document.visibilityState === 'visible') void load(); };
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => { document.removeEventListener('visibilitychange', refreshWhenVisible); };
  }, [load]);
  useEffect(() => {
    const selected = items.find((item) => item.escalation_id === selectedId);
    if (!selected) { setDraft(''); return; }
    const amount = Number((selected.proposed_action.args as Record<string, unknown> | undefined)?.amount ?? 0);
    setDraft(selected.category === 'refund' ? `I’ve approved your $${amount || 299} refund request. It will now be processed according to your payment provider’s timeline.` : 'A human specialist has reviewed your request and will follow up here.');
    setEditing(false); setRejecting(false); setRejectNote('');
  }, [selectedId]);

  const selected = items.find((item) => item.escalation_id === selectedId);
  useEffect(() => {
    if (!selected) { setCustomerDetail(null); setCustomerDetailError(''); return; }
    let active = true;
    setCustomerDetail(null); setCustomerDetailError('');
    getCustomerDetail(selected.customer_id).then((detail) => { if (active) setCustomerDetail(detail); }).catch((exception) => { if (active) setCustomerDetailError(exception instanceof Error ? exception.message : 'Account summary unavailable.'); });
    return () => { active = false; };
  }, [selected?.customer_id, selectedId]);
  useEffect(() => { if (editing) messageRef.current?.focus(); }, [editing]);
  const pending = items.filter((item) => item.status === 'pending');
  const refundCount = pending.filter((item) => item.category === 'refund').length;
  const visible = useMemo(() => items.filter((item) => item.status === status && (reason === 'All reasons' || reasonCode(item) === reason)), [items, reason, status]);

  const submitDecision = async (action: 'approve' | 'edit' | 'reject') => {
    if (!selected) return;
    if (action === 'edit' && !editing) { setEditing(true); return; }
    if (action === 'reject' && !rejecting) { setRejecting(true); return; }
    if (action === 'reject' && !rejectNote.trim()) { notify('Add a short note before rejecting.', 'error'); return; }
    const previous = selected;
    const previousSummary = summary;
    const customerMessage = action === 'reject' ? 'A human specialist reviewed your request. Please reply if you would like help with another option.' : draft.trim();
    const decisionAt = new Date().toISOString();
    setActing(true);
    setItems((current) => current.map((item) => item.escalation_id === selected.escalation_id ? { ...item, status: 'resolved', decision: action, decision_note: action === 'reject' ? rejectNote.trim() : null, customer_message: customerMessage, resolved_at: decisionAt } : item));
    setSummary((current) => current ? {
      ...current,
      awaiting_review: current.awaiting_review === null ? null : Math.max(0, current.awaiting_review - 1),
      refunds_pending_review: selected.category === 'refund' && current.refunds_pending_review !== null ? Math.max(0, current.refunds_pending_review - 1) : current.refunds_pending_review,
    } : current);
    try {
      await decideEscalation(selected.escalation_id, {
        action,
        customer_message: customerMessage,
        note: action === 'reject' ? rejectNote.trim() : undefined,
      });
      window.dispatchEvent(new Event('pulsecheck:escalations-updated'));
      notify('Decision saved. The customer conversation is updating in the background.');
      setEditing(false); setRejecting(false); setRejectNote('');
    } catch (exception) {
      setItems((current) => current.map((item) => item.escalation_id === previous.escalation_id ? previous : item));
      setSummary(previousSummary);
      notify(exception instanceof Error ? exception.message : 'Could not save the decision.', 'error');
    } finally { setActing(false); }
  };

  return <section className="page-content dashboard-page">
    <PageIntro eyebrow="Operations" title="Dashboard" description="Review the moments where an agent needs a human decision." actions={<span className="live-indicator"><span /> Live queue</span>} />

    <div className="kpi-grid">
      <article className="kpi-card"><span className="kpi-icon kpi-icon-warning"><ShieldAlert size={17} /></span><span className="kpi-label">Awaiting review</span><strong>{loading ? '—' : summary?.awaiting_review ?? pending.length}</strong><span className="kpi-foot">Escalations needing a decision</span></article>
      <article className="kpi-card"><span className="kpi-icon kpi-icon-accent"><AlertTriangle size={17} /></span><span className="kpi-label">Refunds pending review</span><strong>{loading ? '—' : summary?.refunds_pending_review ?? refundCount}</strong><span className="kpi-foot">Manager approval required</span></article>
      <article className="kpi-card"><span className="kpi-icon kpi-icon-info"><BadgeCheck size={17} /></span><span className="kpi-label">Open known incidents</span><strong>{loading ? '—' : summary?.open_incidents ?? openIncidents}</strong><span className="kpi-foot">Reported by the technical agent</span></article>
    </div>

    <div className="dashboard-grid">
      <section className="panel queue-panel" aria-labelledby="queue-title">
        <div className="panel-heading">
          <div><div className="panel-kicker">Human review</div><h2 id="queue-title">Escalation queue</h2></div>
          <button className="icon-button" onClick={() => void load()} aria-label="Refresh escalation queue" title="Refresh"><RefreshCw size={16} /></button>
        </div>
        <div className="queue-toolbar">
          <label className="visually-hidden" htmlFor="queue-reason">Filter by reason</label>
          <ThemedSelect
            id="queue-reason"
            className="queue-filter"
            value={reason}
            onChange={setReason}
            options={[{ value: 'All reasons', label: 'All reasons' }, ...Object.entries(reasonLabels).map(([value, label]) => ({ value, label }))]}
          />
          <div className="segmented-control" role="group" aria-label="Queue status">
            <button className={status === 'pending' ? 'is-selected' : ''} aria-pressed={status === 'pending'} onClick={() => setStatus('pending')}>Pending <span>{pending.length}</span></button>
            <button className={status === 'resolved' ? 'is-selected' : ''} aria-pressed={status === 'resolved'} onClick={() => setStatus('resolved')}>Resolved</button>
          </div>
        </div>
        {loading ? <div className="queue-skeleton">{Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="queue-skeleton-row" />)}</div> : error ? <ErrorState message={error} onRetry={() => void load(true)} /> : visible.length === 0 ? <EmptyState title={status === 'pending' ? 'All caught up' : 'No resolved escalations yet'} description={status === 'pending' ? 'New handoffs will appear here.' : 'Resolved decisions will appear here.'} /> : (
          <div className="queue-table-wrap"><table className="queue-table"><thead><tr><th>Customer</th><th>Reason</th><th>Proposed action</th><th>Waiting</th></tr></thead><tbody>
            {visible.map((item) => <tr key={item.escalation_id} className={selectedId === item.escalation_id ? 'is-selected' : ''} onClick={() => setSelectedId(item.escalation_id)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedId(item.escalation_id); } }} aria-selected={selectedId === item.escalation_id}>
              <td><strong>{item.customer_company_name}</strong><small>{item.customer_id}</small></td>
              <td><StatusChip tone={reasonTone(reasonCode(item))}>{reasonLabels[reasonCode(item)] ?? reasonCode(item).replaceAll('_', ' ')}</StatusChip></td>
              <td className="action-cell">{String((item.proposed_action.args as Record<string, unknown> | undefined)?.amount ? `$${(item.proposed_action.args as Record<string, unknown>).amount} refund` : item.proposed_action.type ?? item.category)}</td>
              <td className="waiting-cell"><Clock3 size={13} />{item.status === 'resolved' ? 'Resolved' : elapsedLabel(item.created_at_time || item.created_at)}</td>
            </tr>)}
          </tbody></table></div>
        )}
      </section>

      <section className="panel detail-panel" aria-labelledby="detail-title">
        {!selected ? <EmptyState title="Select an escalation" description="Choose a queue item to review its context and proposed action." /> : <>
          <div className="panel-heading detail-heading"><div><div className="panel-kicker">Review request</div><h2 id="detail-title">{selected.customer_company_name}</h2></div><StatusChip tone={acting ? 'warning' : selected.status === 'pending' ? reasonTone(selected.reasoning) : 'success'}>{acting ? 'Saving decision' : selected.status === 'pending' ? 'Pending review' : 'Resolved'}</StatusChip></div>
          <div className="detail-meta"><span>{selected.customer_id}</span><span>{customerDetail?.subscription?.tier ?? 'Plan loading'}</span><StatusChip tone={customerDetail?.customer.account_status === 'active' ? 'success' : customerDetail?.customer.account_status === 'cancelled' ? 'neutral' : 'warning'}>{customerDetail?.customer.account_status === 'active' ? 'Active' : customerDetail?.customer.account_status === 'cancelled' ? 'Inactive' : customerDetail ? 'Pending' : customerDetailError ? 'Status unavailable' : 'Status loading'}</StatusChip><span>{Math.round(selected.confidence * 100)}% confidence</span></div>
          <div className="detail-section"><h3>Why it was escalated</h3><p>{reasonLabels[reasonCode(selected)] ?? reasonCode(selected).replaceAll('_', ' ')}</p>{selected.reasoning.includes(' — ') && <p className="detail-muted">{selected.reasoning.split(' — ').slice(1).join(' — ')}</p>}<p className="detail-muted">{selected.conversation_summary}</p></div>
          <div className="detail-section"><h3>Agent’s proposed action</h3><pre className="proposal-code">{JSON.stringify(selected.proposed_action, null, 2)}</pre></div>
          <div className="conversation-peek"><div className="conversation-icon"><FileText size={15} /></div><div><strong>Conversation</strong><p>Read the full transcript and the agent’s execution steps.</p></div><button className="text-button" onClick={() => { setSelectedCustomerId(selected.customer_id); navigate(`/chat?thread=${encodeURIComponent(selected.thread_id)}`); }}>Open transcript <ArrowUpRight size={14} /></button></div>
          <div className="detail-section message-section"><label htmlFor="customer-message">Message to customer</label><textarea ref={messageRef} id="customer-message" value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} disabled={selected.status !== 'pending' || !editing} />
            {!editing && selected.status === 'pending' && <span className="field-hint">Suggested reply — select Edit to personalize before sending.</span>}
            {rejecting && <div className="reject-note-wrap"><label htmlFor="reject-note">Short note for the review record</label><div className="reject-note-row"><input id="reject-note" className="text-input" value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} maxLength={500} placeholder="Why is this request being rejected?" /><button className="icon-button" aria-label="Cancel rejection" onClick={() => { setRejecting(false); setRejectNote(''); }}><X size={16} /></button></div></div>}
          </div>
          {selected.status === 'pending' && <div className="decision-actions">
            <Button onClick={() => void submitDecision(editing ? 'edit' : 'approve')} disabled={acting || !draft.trim()}>{acting ? 'Sending…' : editing ? 'Send edited' : 'Approve'}</Button>
            {!editing && <Button variant="secondary" onClick={() => void submitDecision('edit')}>Edit</Button>}
            <Button variant="quiet" className="reject-button" onClick={() => void submitDecision('reject')} disabled={acting}>{rejecting ? 'Confirm reject' : 'Reject'}</Button>
          </div>}
          {selected.status === 'resolved' && <div className="resolved-note">{acting ? <LoaderCircle className="spin" size={15} /> : <BadgeCheck size={15} />}{acting ? 'Saving decision and updating the conversation…' : `Decision recorded${selected.resolved_at ? ` · ${new Date(selected.resolved_at).toLocaleString()}` : ''}`}</div>}
        </>}
      </section>
    </div>
  </section>;
}
