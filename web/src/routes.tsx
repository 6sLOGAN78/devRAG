import { CanvasPage } from './pages/agents/canvas';
import { Routes, Route, Navigate } from 'react-router';
import { LoginNextPage } from './pages/login-next';
import { RegisterPage } from './pages/register';
import { DashboardPage } from './pages/dashboard';
import { MainLayout } from './layouts/main-layout';
import { ProtectedRoute } from './components/ProtectedRoute';

import { DatasetListPage } from './pages/datasets';
import { DatasetDetailPage } from './pages/datasets/detail';
import { ChatPage } from './pages/chat';
import { AdminGuard } from './components/AdminGuard';
import { AdminLayout } from './pages/admin/layout';
import { AdminOverview } from './pages/admin/index';
import { AdminUsers } from './pages/admin/users';


export const AppRoutes = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginNextPage />} />
      <Route path="/register" element={<RegisterPage />} />
      
      <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        
        {/* Knowledge Routes */}
        <Route path="/datasets" element={<DatasetListPage />} />
        <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
        
        
        {/* Admin Routes */}
        <Route path="/admin" element={<AdminGuard><AdminLayout /></AdminGuard>}>
          <Route index element={<AdminOverview />} />
          <Route path="users" element={<AdminUsers />} />
        </Route>

        {/* Placeholders for future routes */}
        <Route path="/documents" element={<div className="p-4 bg-white shadow rounded-lg">Documents (Coming Soon)</div>} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/agents/canvas" element={<CanvasPage />} />
        <Route path="/agents" element={<div className="p-4 bg-white shadow rounded-lg">Agents (Coming Soon)</div>} />
      </Route>
      
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
