import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { LoginNextPage } from './index';
import { DashboardPage } from '../dashboard/index';
import { ProtectedRoute } from '../../components/ProtectedRoute';
import { useAuthStore } from '../../stores/auth-store';
import { apiClient } from '../../utils/authorization-util';
import MockAdapter from 'axios-mock-adapter';
import userEvent from '@testing-library/user-event';

describe('Login Integration', () => {
  let mockAxios: MockAdapter;

  beforeEach(() => {
    mockAxios = new MockAdapter(apiClient);
    useAuthStore.setState({ user: null, isAuthenticated: false, isHydrating: false });
  });

  afterEach(() => {
    mockAxios.restore();
    vi.clearAllMocks();
  });

  const TestApp = () => (
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginNextPage />} />
        <Route 
          path="/dashboard" 
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          } 
        />
      </Routes>
    </MemoryRouter>
  );

  it('renders login form and authenticates successfully', async () => {
    mockAxios.onPost('/user/login').reply(200, {
      token: 'fake-jwt',
      id: '1',
      email: 'user@test.com',
      nickname: 'Test User'
    });

    render(<TestApp />);

    expect(screen.getByText('Sign in to devRAG')).toBeInTheDocument();

    const emailInput = screen.getByLabelText(/Email address/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    const submitBtn = screen.getByRole('button', { name: /Sign in/i });

    await userEvent.type(emailInput, 'user@test.com');
    await userEvent.type(passwordInput, 'Password123');
    
    fireEvent.click(submitBtn);

    // Wait for Dashboard to render
    await waitFor(() => {
      expect(screen.getByText(/Welcome back, Test User/i)).toBeInTheDocument();
    });

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.email).toBe('user@test.com');
  });

  it('displays error on failed login', async () => {
    mockAxios.onPost('/user/login').reply(401, {
      error: 'invalid credentials'
    });

    render(<TestApp />);

    const emailInput = screen.getByLabelText(/Email address/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    const submitBtn = screen.getByRole('button', { name: /Sign in/i });

    await userEvent.type(emailInput, 'wrong@test.com');
    await userEvent.type(passwordInput, 'badpass');
    
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('invalid credentials')).toBeInTheDocument();
    });
  });
});
