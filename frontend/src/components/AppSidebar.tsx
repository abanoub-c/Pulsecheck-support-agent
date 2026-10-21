import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Activity, BarChart3, ChevronDown, ChevronLeft, ChevronRight, Clock3, LayoutDashboard, LoaderCircle, MessageCircle, Monitor, Moon, RotateCcw, Settings2, Sun, Users, X } from 'lucide-react';
import { getCustomerDetail, getEscalations, resetDemo, clearThreadIds, formatDate, daysUntil } from '../lib/api';
import { useApp } from '../lib/AppContext';
import type { CustomerDetail, DemoCustomer } from '../lib/types';

type Props = { collapsed: boolean; mobileOpen: boolean; onToggle: () => void; onCloseMobile: () => void };
const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/clients', label: 'Clients', icon: Users },
  { to: '/chat', label: 'Chat', icon: MessageCircle },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
];
const themeOptions = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
] as const;

let systemThemeQuery: MediaQueryList | null = null;
let systemThemeListener: (() => void) | null = null;
function readTheme() { return localStorage.getItem('pulsecheck-theme') || 'light'; }
function applyTheme(theme: string) {
  localStorage.setItem('pulsecheck-theme', theme);
  if (systemThemeQuery && systemThemeListener) systemThemeQuery.removeEventListener('change', systemThemeListener);
  systemThemeQuery = null; systemThemeListener = null;
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const dark = theme === 'dark' || (theme === 'system' && media.matches);
  document.documentElement.classList.toggle('dark', dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#1C1917' : '#FAFAF9');
  if (theme === 'system') {
    systemThemeQuery = media;
    systemThemeListener = () => {
      document.documentElement.classList.toggle('dark', media.matches);
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', media.matches ? '#1C1917' : '#FAFAF9');
    };
    media.addEventListener('change', systemThemeListener);
  }
}

export function AppSidebar({ collapsed, mobileOpen, onToggle, onCloseMobile }: Props) {
  const { demoCustomers, selectedCustomerId, setSelectedCustomerId, notify, pendingEscalationCount, pendingEscalationRevision, setPendingEscalationCount, adjustPendingEscalationCount } = useApp();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [threadStatus, setThreadStatus] = useState('Open');
  const [theme, setTheme] = useState(readTheme);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const location = useLocation();
  const selected = demoCustomers.find((row) => row.customer_id === selectedCustomerId);
  const railCollapsed = collapsed && !mobileOpen;
  const pendingRevisionRef = useRef(pendingEscalationRevision);
  pendingRevisionRef.current = pendingEscalationRevision;

  useEffect(() => {
    let active = true;
    getCustomerDetail(selectedCustomerId).then((data) => { if (active) setDetail(data); }).catch(() => { if (active) setDetail(null); });
    const refreshPending = () => {
      const revisionAtRequest = pendingRevisionRef.current;
      return getEscalations('pending').then(({ items }) => {
      if (!active) return;
      // Don't let an older request overwrite a count changed by a local action
      // while that request was still in flight.
      if (revisionAtRequest === pendingRevisionRef.current) setPendingEscalationCount(items.length);
      const waiting = items.some((item) => item.customer_id === selectedCustomerId);
      setThreadStatus(waiting ? 'Waiting for a human' : 'Open');
      }).catch(() => undefined);
    };
    void refreshPending();
    const onEscalationsUpdated = (event: Event) => {
      const detail = (event as CustomEvent<{ pendingDelta?: number; refresh?: boolean }>).detail;
      if (typeof detail?.pendingDelta === 'number') adjustPendingEscalationCount(detail.pendingDelta);
      if (detail?.refresh) void refreshPending();
    };
    window.addEventListener('pulsecheck:escalations-updated', onEscalationsUpdated);
    return () => { active = false; window.removeEventListener('pulsecheck:escalations-updated', onEscalationsUpdated); };
  }, [selectedCustomerId, setPendingEscalationCount, adjustPendingEscalationCount]);

  useEffect(() => { setSettingsOpen(false); }, [location.pathname]);

  const reset = async () => {
    if (resetting) return;
    if (!window.confirm('Restore the original demo data? This clears every saved chat and human-review decision, then restores the original sample escalation.')) return;
    setResetting(true);
    try {
      await resetDemo();
      clearThreadIds();
      notify('Original demo data restored, including chats and escalations.');
      // Reload every page so dashboard, analytics, chat history, and queue all
      // refetch the same freshly seeded baseline.
      window.setTimeout(() => window.location.assign(window.location.pathname), 350);
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not reset demo data.', 'error');
    } finally {
      setResetting(false);
    }
  };
  const customerSummary = detail?.subscription;
  const days = daysUntil(customerSummary?.next_billing_date);
  const statusClass = threadStatus === 'Waiting for a human' ? 'status-chip status-warning' : 'status-chip status-neutral';
  const displayDate = days === null ? 'No renewal date' : days < 0 ? `Past due · ${formatDate(customerSummary?.next_billing_date)}` : days === 0 ? 'Renews today' : `Renews in ${days} days`;

  return (
    <>
      {mobileOpen && <button className="drawer-scrim" aria-label="Close navigation" onClick={onCloseMobile} />}
      <aside className={`app-sidebar ${railCollapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'is-mobile-open' : ''}`} role={mobileOpen ? 'dialog' : undefined} aria-modal={mobileOpen || undefined} aria-label="Primary navigation">
        <div className="sidebar-brand-row">
          <NavLink to="/dashboard" className="brand-link" onClick={onCloseMobile} aria-label="Pulsecheck Support home">
            <span className="brand-mark"><Activity size={18} strokeWidth={2.2} /></span>
            {!railCollapsed && <span className="brand-wordmark">Pulsecheck <strong>Support</strong></span>}
          </NavLink>
          <button className="icon-button collapse-button" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
          <button className="icon-button mobile-close" onClick={onCloseMobile} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <nav className="primary-nav" aria-label="Main">
          <div className="nav-caption">Workspace</div>
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={onCloseMobile} className={({ isActive }) => `nav-item ${isActive ? 'is-active' : ''}`} title={railCollapsed ? label : undefined}>
              <span className="nav-icon"><Icon size={18} strokeWidth={1.8} /></span>
              {!railCollapsed && <span className="nav-label">{label}</span>}
              {label === 'Dashboard' && pendingEscalationCount > 0 && <span className="nav-count" aria-label={`${pendingEscalationCount} pending escalations`}>{pendingEscalationCount}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-settings">
          <div className="nav-caption settings-caption">Settings</div>
          {railCollapsed ? (
            <div className="collapsed-settings-wrap">
              <button className={`nav-item settings-trigger ${settingsOpen ? 'is-active' : ''}`} onClick={() => setSettingsOpen((value) => !value)} aria-expanded={settingsOpen} aria-label="Open demo settings" title="Demo settings"><Settings2 size={18} /></button>
              {settingsOpen && <div className="settings-popover" role="dialog" aria-label="Demo settings">
                <CustomerPicker id="customer-collapsed" label="Chatting as" customers={demoCustomers} selectedId={selectedCustomerId} onSelect={setSelectedCustomerId} />
                <ThemeSelector theme={theme} onChange={(value) => { setTheme(value); applyTheme(value); }} />
                {resetting && <div className="reset-progress" role="status" aria-live="polite"><LoaderCircle className="spin" size={15} /> Restoring original demo data…</div>}
                <button className="button button-secondary button-full" onClick={reset} disabled={resetting} aria-busy={resetting}>
                  {resetting ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />}
                  {resetting ? 'Resetting…' : 'Reset demo data'}
                </button>
              </div>}
            </div>
          ) : (
            <div className="customer-switcher">
              <CustomerPicker id="chatting-as" label="Chatting as" customers={demoCustomers} selectedId={selectedCustomerId} onSelect={setSelectedCustomerId} />
              <div className="customer-summary">
                <span className="summary-company">{selected?.company ?? 'Loading customer…'}</span>
                <span className="summary-plan">{(customerSummary?.tier ?? selected?.tier ?? '—').replace(/^./, (letter) => letter.toUpperCase())} plan <span>·</span> ${customerSummary?.price_monthly ?? '—'}/mo</span>
                <span className="summary-date"><Clock3 size={12} /> {displayDate}</span>
                <span className={statusClass}><span className="status-dot" />{threadStatus}</span>
              </div>
              <ThemeSelector theme={theme} onChange={(value) => { setTheme(value); applyTheme(value); }} />
              {resetting && <div className="reset-progress" role="status" aria-live="polite"><LoaderCircle className="spin" size={15} /> Restoring original demo data…</div>}
              <button className="reset-button" onClick={reset} disabled={resetting} aria-busy={resetting}>
                {resetting ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}
                {resetting ? 'Resetting demo data…' : 'Reset demo data'}
              </button>
            </div>
          )}
        </div>

        <div className="sidebar-spacer" />
        <div className={`demo-chip ${railCollapsed ? 'demo-chip-collapsed' : ''}`} title="Sample data only">
          <span className="demo-dot" />{!railCollapsed && <span>Demo mode, sample data</span>}
        </div>
      </aside>
    </>
  );
}

function CustomerPicker({ id, label, customers, selectedId, onSelect }: { id: string; label: string; customers: DemoCustomer[]; selectedId: string; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLDivElement | null>>([]);
  const selectedIndex = Math.max(0, customers.findIndex((customer) => customer.customer_id === selectedId));
  const selected = customers[selectedIndex];
  const listboxId = `${id}-options`;

  useEffect(() => { if (open) optionRefs.current[activeIndex]?.focus(); }, [open, activeIndex]);
  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, [open]);

  const choose = (customer: DemoCustomer) => {
    onSelect(customer.customer_id);
    setOpen(false);
    triggerRef.current?.focus();
  };
  const moveActive = (index: number) => {
    const next = (index + customers.length) % customers.length;
    setActiveIndex(next);
    optionRefs.current[next]?.focus();
  };
  const onTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(selectedIndex);
      setOpen(true);
    }
  };
  const onOptionKeyDown = (event: KeyboardEvent<HTMLDivElement>, index: number) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); moveActive(index + 1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); moveActive(index - 1); }
    else if (event.key === 'Home') { event.preventDefault(); moveActive(0); }
    else if (event.key === 'End') { event.preventDefault(); moveActive(customers.length - 1); }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (customers[index]) choose(customers[index]); }
    else if (event.key === 'Escape') { event.preventDefault(); setOpen(false); triggerRef.current?.focus(); }
  };

  return <div ref={rootRef} className={`customer-picker ${open ? 'is-open' : ''}`} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <label className="field-label" htmlFor={id}>{label}</label>
    <button ref={triggerRef} id={id} type="button" className="customer-picker-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={listboxId} aria-label={`${label}: ${selected?.company ?? 'Loading customers'}`} onClick={() => { setActiveIndex(selectedIndex); setOpen((value) => !value); }} onKeyDown={onTriggerKeyDown}>
      <span className="customer-picker-value"><span className="customer-picker-company">{selected?.company ?? 'Loading customers…'}</span>{selected && <span className="customer-picker-id">{selected.customer_id}</span>}</span>
      <ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && <div id={listboxId} className="customer-picker-options" role="listbox" aria-label="Choose a customer">
      {customers.map((customer, index) => <div key={customer.customer_id} ref={(element) => { optionRefs.current[index] = element; }} role="option" aria-selected={customer.customer_id === selectedId} tabIndex={activeIndex === index ? 0 : -1} className="customer-picker-option" onClick={() => choose(customer)} onKeyDown={(event) => onOptionKeyDown(event, index)}>
        <span className="customer-picker-company">{customer.company}</span><span className="customer-picker-id">{customer.customer_id}</span>
      </div>)}
    </div>}
  </div>;
}

function ThemeSelector({ theme, onChange }: { theme: string; onChange: (value: string) => void }) {
  return <div className="theme-control" role="group" aria-label="Theme">
    {themeOptions.map(({ value, label, icon: Icon }) => <button key={value} className={`theme-choice ${theme === value ? 'is-selected' : ''}`} aria-pressed={theme === value} onClick={() => onChange(value)} title={label}><Icon size={14} /><span>{label}</span></button>)}
  </div>;
}
