// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { ToastContainer } from './components/Toast';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { MigrationEntryPage } from './pages/MigrationEntryPage';
import { MigrationWizardPage } from './pages/MigrationWizardPage';
import { JobMonitorPage } from './pages/JobMonitorPage';
import { VMsPage } from './pages/VMsPage';
import { KubeVirtPage } from './pages/KubeVirtPage';
import { KubeconfigsPage } from './pages/KubeconfigsPage';
import { NetworksPage } from './pages/NetworksPage';
import { SettingsPage } from './pages/SettingsPage';
import { ApiDocsPage } from './pages/ApiDocsPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { AboutPage } from './pages/AboutPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { useAuthStore } from './stores/auth';
import { WebSocketProvider } from './contexts/WebSocketContext';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5000, retry: 1 },
  },
});

export default function App() {
  const { isAuthenticated, loading, checkSession } = useAuthStore();

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center dashboard-liquid-glass">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <div className="text-sm text-zinc-500">Loading...</div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <QueryClientProvider client={queryClient}>
        <LoginPage />
      </QueryClientProvider>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/providers" element={<ProvidersPage />} />
            <Route path="/migrate" element={<MigrationEntryPage />} />
            <Route path="/migrate/wizard" element={<MigrationWizardPage />} />
            <Route path="/jobs" element={<JobMonitorPage />} />
            <Route path="/vms" element={<VMsPage />} />
            <Route path="/kubevirt" element={<KubeVirtPage />} />
            <Route path="/kubeconfigs" element={<KubeconfigsPage />} />
            <Route path="/networks" element={<NetworksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/api-docs" element={<ApiDocsPage />} />
            <Route path="/audit" element={<AuditLogPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <ToastContainer />
      </WebSocketProvider>
    </QueryClientProvider>
  );
}
