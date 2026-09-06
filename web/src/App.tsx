import { useEffect } from 'react';
import { BrowserRouter } from 'react-router';
import { AppRoutes } from './routes';
import { useAuthStore } from './stores/auth-store';

function App() {
  const { hydrate, isHydrating } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (isHydrating) {
    return <div className="flex h-screen items-center justify-center bg-gray-50">Loading application...</div>;
  }

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
