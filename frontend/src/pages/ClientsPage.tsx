import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight, ChevronLeft, ChevronRight, ExternalLink, Search, X } from 'lucide-react';
import { getCustomerDetail, getCustomers, formatDate } from '../lib/api';
import { useApp } from '../lib/AppContext';
import type { CustomerDetail, CustomerRow } from '../lib/types';
import { Button, EmptyState, ErrorState, PageIntro, Skeleton, StatusChip } from '../components/ui/Primitives';

const columns = [
  { key: 'customer_id', label: 'Client ID' },
  { key: 'company_name', label: 'Name' },
  { key: 'contact_email', label: 'Email' },
  { key: 'status', label: 'Status' },
  { key: 'assigned_category', label: 'Assigned category' },
  { key: 'signup_date', label: 'Date added' },
] as const;
type SortKey = typeof columns[number]['key'] | 'none';
function statusTone(status: CustomerRow['status']): 'success' | 'warning' | 'neutral' { return status === 'Active' ? 'success' : status === 'Pending' ? 'warning' : 'neutral'; }
function niceCategory(category: string) { return category.charAt(0).toUpperCase() + category.slice(1); }

export default function ClientsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const paramsKey = searchParams.toString();
  const params = useMemo(() => new URLSearchParams(paramsKey), [paramsKey]);
  const q = params.get('q') ?? '';
  const status = params.get('status') ?? 'All';
  const category = params.get('category') ?? 'All';
  const sort = (params.get('sort') ?? 'company_name') as SortKey;
  const dir = params.get('dir') ?? 'asc';
  const page = Number(params.get('page') ?? 1);
  const pageSize = Number(params.get('page_size') ?? 10);
  const [searchDraft, setSearchDraft] = useState(q);
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [drawerId, setDrawerId] = useState('');
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const drawerRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const { demoCustomers, setSelectedCustomerId } = useApp();
  const navigate = useNavigate();
  const allowlisted = useMemo(() => new Set(demoCustomers.map((item) => item.customer_id)), [demoCustomers]);

  const update = useCallback((patch: Record<string, string | number | undefined>, resetPage = false) => {
    const next = new URLSearchParams(paramsKey);
    Object.entries(patch).forEach(([key, value]) => {
      if (value === undefined || value === '' || (key === 'page' && value === 1)) next.delete(key);
      else next.set(key, String(value));
    });
    if (resetPage && !('page' in patch)) next.delete('page');
    setSearchParams(next, { replace: true });
  }, [paramsKey, setSearchParams]);

  useEffect(() => { setSearchDraft(q); }, [q]);
  useEffect(() => {
    if (searchDraft === q) return;
    const timer = window.setTimeout(() => update({ q: searchDraft, page: 1 }), 200);
    return () => window.clearTimeout(timer);
  }, [searchDraft, q, update]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getCustomers({ q, status, category, sort, dir, page, page_size: pageSize }).then((data) => {
      if (!active) return;
      setRows(data.items); setTotal(data.total); setError('');
    }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : 'Unable to load clients.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [q, status, category, sort, dir, page, pageSize, reloadKey]);

  const openDetails = async (customerId: string) => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDrawerId(customerId); setDetail(null); setDetailError(''); setDetailLoading(true);
    try { setDetail(await getCustomerDetail(customerId)); }
    catch (exception) { setDetailError(exception instanceof Error ? exception.message : 'Unable to load client details.'); }
    finally { setDetailLoading(false); }
  };
  useEffect(() => {
    if (!drawerId) return;
    const drawer = drawerRef.current;
    document.body.classList.add('client-drawer-open');
    drawer?.querySelector<HTMLElement>('[aria-label="Close client details"]')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setDrawerId(''); return; }
      if (event.key !== 'Tab' || !drawer) return;
      const focusable = [...drawer.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')].filter((node) => node.offsetParent !== null);
      if (!focusable.length) { event.preventDefault(); drawer.focus(); return; }
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !drawer.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !drawer.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.classList.remove('client-drawer-open');
      openerRef.current?.focus();
    };
  }, [drawerId]);
  const sortColumn = (key: SortKey) => {
    if (sort !== key) update({ sort: key, dir: 'asc', page: 1 });
    else if (dir === 'asc') update({ sort: key, dir: 'desc', page: 1 });
    else if (dir === 'desc') update({ sort: 'none', dir: 'asc', page: 1 });
    else update({ sort: key, dir: 'asc', page: 1 });
  };
  const clearFilters = () => { setSearchDraft(''); setSearchParams(new URLSearchParams(), { replace: true }); };
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  return <section className="page-content clients-page">
    <PageIntro eyebrow="Workspace / Records" title="Clients" description="A searchable preview of the customer records behind the demo." actions={<span className="data-count-pill">{total} records</span>} />
    <section className="panel clients-panel" aria-label="Client database preview">
      <div className="client-toolbar">
        <div className="search-field"><Search size={16} /><label className="visually-hidden" htmlFor="client-search">Search clients</label><input id="client-search" type="search" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search ID, company, contact or email…" /></div>
        <label className="filter-field"><span>Status</span><select className="select-control" value={status} onChange={(event) => update({ status: event.target.value, page: 1 })}><option>All</option><option>Active</option><option>Inactive</option><option>Pending</option></select></label>
        <label className="filter-field"><span>Category</span><select className="select-control" value={category} onChange={(event) => update({ category: event.target.value, page: 1 })}><option>All</option><option value="billing">Billing</option><option value="technical">Technical</option><option value="refund">Refund</option><option value="other">Other</option></select></label>
        <button className="clear-filters" onClick={clearFilters} disabled={!q && status === 'All' && category === 'All'}>Clear filters <X size={13} /></button>
      </div>
      <div className="table-caption"><span>{loading ? 'Loading records…' : total ? `Showing ${first} to ${last} of ${total}` : 'No records'}</span><span className="table-caption-right">Sample CRM data <span className="demo-dot" /></span></div>
      {loading ? <div className="clients-skeleton"><Skeleton className="table-skeleton-head" />{Array.from({ length: pageSize < 10 ? pageSize : 8 }, (_, index) => <Skeleton key={index} className="table-skeleton-row" />)}</div> : error ? <ErrorState message={error} onRetry={() => setReloadKey((value) => value + 1)} /> : rows.length === 0 ? <EmptyState title="No clients match these filters" description="Try adjusting your search or clearing one of the filters." action={<Button variant="secondary" onClick={clearFilters}>Clear filters</Button>} /> : (
        <div className="clients-table-scroll"><table className="clients-table"><thead><tr>{columns.map((column) => <th key={column.key} aria-sort={sort === column.key ? dir === 'asc' ? 'ascending' : 'descending' : 'none'}><button className="sort-heading" onClick={() => sortColumn(column.key)}>{column.label}{sort === column.key ? dir === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} /> : <ArrowUpDown size={13} />}</button></th>)}<th><span className="actions-heading">Actions</span></th></tr></thead><tbody>
          {rows.map((row) => <tr key={row.customer_id}>
            <td><span className="mono-id">{row.customer_id}</span></td>
            <td><div className="company-cell"><strong>{row.company_name}</strong><small>{row.contact_name}</small></div></td>
            <td><a className="email-link" href={`mailto:${row.contact_email}`}>{row.contact_email}</a></td>
            <td><StatusChip tone={statusTone(row.status)}>{row.status}</StatusChip></td>
            <td><span className={`category-pill category-${row.assigned_category}`}>{niceCategory(row.assigned_category)}</span></td>
            <td className="date-cell">{formatDate(row.signup_date)}</td>
            <td><div className="row-actions"><button className="row-action" onClick={() => void openDetails(row.customer_id)} title="View client details">View <ExternalLink size={13} /></button><span className="allowlist-tooltip" title={allowlisted.has(row.customer_id) ? 'Open this client in chat' : 'This customer is unavailable for chat'}><button className="row-action" disabled={!allowlisted.has(row.customer_id)} aria-label={`Chat with ${row.company_name}`} onClick={() => { setSelectedCustomerId(row.customer_id); navigate('/chat'); }}>Chat <ArrowUpRight size={13} /></button></span></div></td>
          </tr>)}
        </tbody></table></div>
      )}
      <div className="table-footer"><span>{total ? `Page ${page} of ${pageCount}` : ' '}</span><div className="pagination-controls"><label className="page-size-label">Rows <select className="select-control page-size-select" value={pageSize} onChange={(event) => update({ page_size: Number(event.target.value), page: 1 })}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label><button className="icon-button pagination-button" aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: Math.max(1, page - 1) })}><ChevronLeft size={17} /></button><button className="icon-button pagination-button" aria-label="Next page" disabled={page >= pageCount} onClick={() => update({ page: page + 1 })}><ChevronRight size={17} /></button></div></div>
    </section>

    {drawerId && <div className="drawer-layer"><button className="drawer-scrim" aria-label="Close client details" onClick={() => setDrawerId('')} /><aside ref={drawerRef} className="client-drawer" role="dialog" aria-modal="true" aria-labelledby="client-drawer-title" tabIndex={-1}>
      <div className="drawer-heading"><div><span className="panel-kicker">Client record</span><h2 id="client-drawer-title">{detail?.customer.company_name ?? 'Client details'}</h2></div><button className="icon-button" aria-label="Close client details" onClick={() => setDrawerId('')}><X size={18} /></button></div>
      {detailLoading ? <div className="drawer-skeleton"><Skeleton /><Skeleton /><Skeleton /></div> : detailError ? <ErrorState message={detailError} onRetry={() => void openDetails(drawerId)} /> : detail && <>
        <div className="detail-meta drawer-meta"><span className="mono-id">{detail.customer.customer_id}</span><StatusChip tone={statusTone(detail.customer.account_status === 'active' ? 'Active' : detail.customer.account_status === 'cancelled' ? 'Inactive' : 'Pending')}>{detail.customer.account_status.replace('_', ' ')}</StatusChip></div>
        <div className="drawer-section"><h3>Contact</h3><p>{detail.customer.contact_name}</p><a className="email-link" href={`mailto:${detail.customer.contact_email}`}>{detail.customer.contact_email}</a></div>
        <div className="drawer-section"><h3>Subscription</h3>{detail.subscription ? <div className="subscription-card"><strong>{detail.subscription.tier} plan</strong><span>${detail.subscription.price_monthly}/mo</span><span>{detail.subscription.monitors_used} of {detail.subscription.monitor_limit} monitors used</span><span>Next billing · {formatDate(detail.subscription.next_billing_date)}</span></div> : <p>No subscription details.</p>}</div>
        <div className="drawer-section"><h3>Recent tickets</h3>{detail.recent_tickets.length ? detail.recent_tickets.map((ticket) => <div className="recent-ticket" key={ticket.ticket_id}><span className="ticket-category">{niceCategory(ticket.category)}</span><strong>{ticket.subject}</strong><small>{formatDate(ticket.created_at)} · {ticket.status}</small></div>) : <p>No recent tickets.</p>}</div>
        <div className="drawer-footer"><Button variant="secondary" onClick={() => setDrawerId('')}>Close</Button><span className="allowlist-tooltip" title={detail.chat_allowed ? 'Open chat' : 'This customer is unavailable for chat'}><Button disabled={!detail.chat_allowed} onClick={() => { setSelectedCustomerId(drawerId); setDrawerId(''); navigate('/chat'); }}>Open in chat <ArrowUpRight size={15} /></Button></span></div>
      </>}
    </aside></div>}
  </section>;
}
