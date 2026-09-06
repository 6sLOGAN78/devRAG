import { useAuthStore } from '../../stores/auth-store';

export const DashboardPage = () => {
  const { user } = useAuthStore();

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-2xl font-bold text-gray-800 mb-4">Welcome back, {user?.nickname || user?.email}</h2>
      <p className="text-gray-600">
        This is the devRAG application shell. Future features will be accessible from the sidebar.
      </p>
    </div>
  );
};
