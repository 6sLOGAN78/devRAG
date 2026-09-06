import { useState, useEffect } from 'react';
import { apiClient } from '../../utils/authorization-util';
import { Users, FileText, Database, MessageSquare } from 'lucide-react';

interface Stats {
  total_users: number;
  total_documents: number;
  total_datasets: number;
  total_chats: number;
}

export const AdminOverview = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await apiClient.get<{ data: Stats }>('/admin/stats');
        setStats(response.data.data);
      } catch (err: any) {
        setError(err.response?.data?.error?.message || 'Failed to load statistics');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) return <div className="text-gray-500">Loading statistics...</div>;
  if (error) return <div className="text-red-500 bg-red-50 p-4 rounded-md">{error}</div>;
  if (!stats) return null;

  const cards = [
    { label: 'Total Users', value: stats.total_users, icon: Users, color: 'text-blue-600', bg: 'bg-blue-100' },
    { label: 'Total Datasets', value: stats.total_datasets, icon: Database, color: 'text-purple-600', bg: 'bg-purple-100' },
    { label: 'Total Documents', value: stats.total_documents, icon: FileText, color: 'text-green-600', bg: 'bg-green-100' },
    { label: 'Chat Sessions', value: stats.total_chats, icon: MessageSquare, color: 'text-orange-600', bg: 'bg-orange-100' },
  ];

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-gray-900">Tenant Overview</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="bg-white rounded-xl shadow-sm p-6 flex items-center space-x-4 border border-gray-100">
              <div className={`p-3 rounded-lg ${card.bg}`}>
                <Icon className={`w-6 h-6 ${card.color}`} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">{card.label}</p>
                <p className="text-2xl font-semibold text-gray-900">{card.value}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
