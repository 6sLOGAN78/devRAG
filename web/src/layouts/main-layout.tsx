import { Outlet, NavLink, useNavigate, useLocation } from 'react-router';
import { useAuthStore } from '../stores/auth-store';
import { Home, FileText, Database, MessageSquare, Settings, LogOut, Bot } from 'lucide-react';

export const MainLayout = () => {
  const { user, logout, isHydrating } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  if (isHydrating) {
    return <div className="flex h-screen items-center justify-center">Loading...</div>;
  }

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: Home },
    { name: 'Knowledge', path: '/datasets', icon: Database },
    { name: 'Documents', path: '/documents', icon: FileText },
    { name: 'Chat', path: '/chat', icon: MessageSquare },
    { name: 'Agents Canvas', path: '/agents/canvas', icon: Bot },
  ];

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <aside className="w-64 bg-white shadow-md flex flex-col">
        <div className="p-4 flex items-center justify-center border-b">
          <h1 className="text-xl font-bold text-gray-800">devRAG</h1>
        </div>
        
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            return (
              <NavLink
                key={item.name}
                to={item.path}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive 
                    ? 'bg-blue-50 text-blue-700 font-medium' 
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t space-y-1">
          <button
            onClick={() => {}}
            className="flex items-center space-x-3 px-4 py-3 w-full text-left rounded-lg text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <Settings className="w-5 h-5" />
            <span>Settings</span>
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center space-x-3 px-4 py-3 w-full text-left rounded-lg text-red-600 hover:bg-red-50 transition-colors"
          >
            <LogOut className="w-5 h-5" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white shadow-sm h-16 flex items-center justify-end px-6">
          <div className="flex items-center space-x-4">
            {user?.tenant_id && (
              <span className="text-xs px-2 py-1 bg-gray-100 rounded border font-mono">
                Tenant: {user.tenant_id}
              </span>
            )}
            <span className="text-sm font-medium text-gray-700">{user?.email}</span>
          </div>
        </header>
        <div className="flex-1 overflow-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
