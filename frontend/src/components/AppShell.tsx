import { useEffect, useState, type ReactNode } from 'react';
import { Menu, X } from 'lucide-react';
import { AppSidebar } from './AppSidebar';
import { useApp } from '../lib/AppContext';

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('pulsecheck-sidebar-collapsed') === 'true');
  const [mobileOpen, setMobileOpen] = useState(false);
  const { toasts, dismissToast } = useApp();
  const toggleCollapsed = () => setCollapsed((value) => {
    localStorage.setItem('pulsecheck-sidebar-collapsed', String(!value));
    return !value;
  });

  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); };
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const drawer = document.querySelector<HTMLElement>('.app-sidebar.is-mobile-open');
      if (!drawer) return;
      const focusable = [...drawer.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), select:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')].filter((item) => item.offsetParent !== null);
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (!drawer.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', closeOnEscape);
    document.addEventListener('keydown', trapFocus);
    document.body.classList.add('drawer-open');
    document.querySelector<HTMLElement>('.app-sidebar .mobile-close')?.focus();
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      document.removeEventListener('keydown', trapFocus);
      document.body.classList.remove('drawer-open');
      previous?.focus?.();
    };
  }, [mobileOpen]);

  return <div className="app-frame">
    <AppSidebar collapsed={collapsed} mobileOpen={mobileOpen} onToggle={toggleCollapsed} onCloseMobile={() => setMobileOpen(false)} />
    <main className={`main-workspace ${collapsed ? 'workspace-collapsed' : ''}`}>
      <button className="mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
      {children}
    </main>
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => <div key={toast.id} className={`toast toast-${toast.tone}`} role="status"><span>{toast.message}</span><button className="toast-close" aria-label="Dismiss notification" onClick={() => dismissToast(toast.id)}><X size={14} /></button></div>)}
    </div>
  </div>;
}
