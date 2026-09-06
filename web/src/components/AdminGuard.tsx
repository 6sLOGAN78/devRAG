import { Navigate } from 'react-router';
import { useAuthStore } from '../stores/auth-store';

export const AdminGuard = ({ children }: { children: React.ReactNode }) => {
  const { user, isAuthenticated, isHydrating } = useAuthStore();

  if (isHydrating) {
    return <div className="flex h-screen items-center justify-center">Loading...</div>;
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== 'admin' && user.role !== 'owner') {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <h1 className="text-4xl font-bold text-red-600">403 Forbidden</h1>
        <p className="text-gray-600">You do not have administrative privileges to view this page.</p>
      </div>
    );
  }

  return <>{children}</>;
};
