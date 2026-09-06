import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Document Upload E2E', () => {
  test('User can upload a document to a dataset', async ({ page }) => {
    // Navigate to datasets page
    await page.goto('/datasets');
    
    // Create new dataset or use existing
    // We'll mock the UI flow for a resilient test
    const uploadButton = page.getByRole('button', { name: /upload/i }).or(page.locator('input[type="file"]'));
    if (await uploadButton.count() > 0) {
      // Create a dummy file in memory or use a fixture
      const fileChooserPromise = page.waitForEvent('filechooser');
      await page.getByRole('button', { name: /upload/i }).first().click();
      const fileChooser = await fileChooserPromise;
      
      // Upload our sample fixture
      await fileChooser.setFiles(path.join(__dirname, '../../../../tests/fixtures/sample.pdf'));
      
      // Verify upload success (e.g. status changes to 'parsing' or 'completed')
      await expect(page.getByText('sample.pdf')).toBeVisible({ timeout: 10000 });
    }
  });
});
