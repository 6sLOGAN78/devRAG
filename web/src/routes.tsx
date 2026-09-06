import { Routes, Route, Navigate } from 'react-router';
import { LoginNextPage } from './pages/login-next';
import { RegisterPage } from './pages/register';
import { DashboardPage } from './pages/dashboard';
import { MainLayout } from './layouts/main-layout';
import { ProtectedRoute } from './components/ProtectedRoute';

export const AppRoutes = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginNextPage />} />
      <Route path="/register" element={<RegisterPage />} />
      
      <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        
        {/* Placeholders for future routes */}
        <Route path="/knowledge" element={<div className="p-4 bg-white shadow rounded-lg">Knowledge Base (Coming Soon)</div>} />
        <Route path="/documents" element={<div className="p-4 bg-white shadow rounded-lg">Documents (Coming Soon)</div>} />
        <Route path="/chat" element={<div className="p-4 bg-white shadow rounded-lg">Chat (Coming Soon)</div>} />
        <Route path="/agents" element={<div className="p-4 bg-white shadow rounded-lg">Agents (Coming Soon)</div>} />
      </Route>
      
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
