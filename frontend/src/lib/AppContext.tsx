import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getDemoCustomers } from './api';
import type { DemoCustomer } from './types';

type Toast = { id: string; message: string; tone: 'success' | 'error' | 'info' };
type AppContextValue = {
  selectedCustomerId: string;
  setSelectedCustomerId: (id: string) => void;
  demoCustomers: DemoCustomer[];
  notify: (message: string, tone?: Toast['tone']) => void;
  toasts: Toast[];
  dismissToast: (id: string) => void;
};
const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [selectedCustomerId, setSelectedCustomerIdState] = useState(() => localStorage.getItem('pulsecheck-customer') || 'CUST-0012');
  const [demoCustomers, setDemoCustomers] = useState<DemoCustomer[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => { getDemoCustomers().then(setDemoCustomers).catch(() => setDemoCustomers([])); }, []);
  const setSelectedCustomerId = (id: string) => {
    setSelectedCustomerIdState(id);
    localStorage.setItem('pulsecheck-customer', id);
  };
  const notify = (message: string, tone: Toast['tone'] = 'success') => {
    const id = crypto.randomUUID();
    setToasts((items) => [...items, { id, message, tone }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 3600);
  };
  const dismissToast = (id: string) => setToasts((items) => items.filter((item) => item.id !== id));
  const value = useMemo(() => ({ selectedCustomerId, setSelectedCustomerId, demoCustomers, notify, toasts, dismissToast }), [selectedCustomerId, demoCustomers, toasts]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('useApp must be used within AppProvider');
  return value;
}
