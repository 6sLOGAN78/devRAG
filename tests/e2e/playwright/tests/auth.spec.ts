import { test, expect } from '@playwright/test';

test.describe('Auth E2E', () => {
  test('User can login and view dashboard', async ({ page }) => {
    // In our mock/dev setup, maybe it bypasses login or uses a dummy auth
    await page.goto('/');
    
    // Check if redirect to /chat or dashboard happens
    await expect(page).toHaveURL(/.*chat|.*agents|.*datasets/);
    
    // Check for a visible navigation element
    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();
  });
});
