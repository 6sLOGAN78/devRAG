import { test, expect } from '@playwright/test';

test.describe('Chat E2E', () => {
  test('User can start a chat and receive a response', async ({ page }) => {
    await page.goto('/chat');
    
    // Wait for the app to initialize
    await page.waitForSelector('textarea[placeholder="Type a message..."]', { state: 'visible' });

    // Send a message
    const input = page.locator('textarea[placeholder="Type a message..."]');
    await input.fill('Hello integration test!');
    await input.press('Enter');

    // Verify user message appears in the chat
    await expect(page.locator('.chat-bubble.user').last()).toContainText('Hello integration test!');

    // Wait for assistant response
    // Depending on the mock or real LLM backend, it could take a moment. 
    // We expect the streaming bubble to appear
    const assistantBubble = page.locator('.chat-bubble.assistant').last();
    await expect(assistantBubble).toBeVisible({ timeout: 15000 });

    // Ensure it contains text (streaming might still be ongoing)
    await expect(assistantBubble).not.toBeEmpty();
  });
});
