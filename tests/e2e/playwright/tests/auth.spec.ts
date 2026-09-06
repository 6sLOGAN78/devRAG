import { test, expect } from '@playwright/test';

test.describe('Auth E2E', () => {
  test('User can login and view dashboard', async ({ page }) => {
    // Navigate to root, should redirect to login
    await page.goto('/');
    await expect(page).toHaveURL(/.*\/login/);

    // Enter credentials
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'Password123');
    
    // Click submit
    await page.click('button[type="submit"]');

    // Wait for navigation to dashboard or chat
    await page.waitForURL(/.*dashboard|.*chat|.*datasets/, { timeout: 10000 });
    
    // Check for a visible navigation element
    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();
  });
});
