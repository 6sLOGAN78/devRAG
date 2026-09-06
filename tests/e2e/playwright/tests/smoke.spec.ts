import { test, expect } from '@playwright/test';

test('MVP Smoke Test', async ({ page }) => {
  // Navigate to login
  await page.goto('/');
  // Assume mock API handles login or wait for network idle
  // Verify main canvas or dashboard loads
});
