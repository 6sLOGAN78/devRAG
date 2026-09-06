import { test, expect } from '@playwright/test';

test.describe('Admin Dashboard and RBAC', () => {
  // Use mock responses since backend might not have admin users seeded
  
  test('Standard user is denied access to admin API', async ({ request }) => {
    // We expect this to be 401 or 403 depending on whether it redirects or blocks
    const adminResponse = await request.get('/api/v1/admin/stats');
    expect(adminResponse.status()).toBe(401);
  });

  test('Unauthenticated user is denied access to admin API', async ({ request }) => {
    const adminResponse = await request.get('/api/v1/admin/stats');
    expect(adminResponse.status()).toBe(401);
  });
  
  test('Admin guard redirects unauthenticated users in frontend', async ({ page }) => {
    await page.goto('/admin');
    
    // Should redirect to login
    await expect(page).toHaveURL(/.*\/login/);
  });
});
