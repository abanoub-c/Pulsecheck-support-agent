import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppProvider } from './lib/AppContext';
import { AppShell } from './components/AppShell';
import './styles/pages.css';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ClientsPage = lazy(() => import('./pages/ClientsPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <AppShell>
          <Suspense fallback={<div className="page-loading" role="status">Loading page…</div>}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/clients" element={<ClientsPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </AppShell>
      </BrowserRouter>
    </AppProvider>
  );
}
