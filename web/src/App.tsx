import { useEffect } from 'react';
import { BrowserRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppRoutes } from './routes';
import { useAuthStore } from './stores/auth-store';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  const { hydrate, isHydrating } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (isHydrating) {
    return <div className="flex h-screen items-center justify-center bg-gray-50">Loading application...</div>;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
