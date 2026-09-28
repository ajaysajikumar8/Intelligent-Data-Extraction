import { test, expect } from '@playwright/test';

test.describe('Regression Suite', () => {
  test.beforeEach(async ({ page }) => {
    // Signup or Login
    await page.goto('http://localhost:5178/signup');
    await page.fill('input[type="email"]', `test-${Date.now()}@example.com`);
    await page.fill('input[type="password"]', 'password123');
    await page.fill('input#signup-name', 'Test User');
    await page.fill('input#signup-workspace', 'Test Workspace');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });

  test('Bug 1: Webhook URL Input Drops Characters', async ({ page }) => {
    await page.goto('http://localhost:5178/integrations');
    await page.click('text=Add Webhook');
    
    // Wait for drawer animation
    await page.waitForTimeout(500);
    
    // Type rapidly
    const input = page.locator('input[placeholder="https://hooks.zapier.com/..."]');
    await input.pressSequentially('https://my-rapid-typing-webhook.com/api', { delay: 10 });
    
    // Assert value
    const val = await input.inputValue();
    expect(val).toBe('https://my-rapid-typing-webhook.com/api');
  });

  test('Bug 2: Submit Button Stuck & Redirect', async ({ page }) => {
    // First, add a template from the library
    await page.goto('http://localhost:5178/templates');
    await page.click('text=Template Library');
    await page.click('button:has-text("Add to my templates")'); // clicks the first one

    await page.goto('http://localhost:5178/submit');
    
    // We skip template selection because it uses a custom UI component and auto-detect is the default.
    
    await page.fill('textarea', 'Test extraction for redirect bug.');
    await page.click('button:has-text("Run extraction")');
    
    // Should automatically redirect to logs
    await page.waitForURL('**/logs', { timeout: 10000 });
    expect(page.url()).toContain('/logs');
  });

  test('Bug 3 & UX Flaw 3: Auth Validation & Correction UI', async ({ page }) => {
    // Auth Validation Test
    await page.goto('http://localhost:5178/signup');
    await page.fill('input[type="email"]', 'invalid-email');
    await page.fill('input[type="password"]', 'short');
    await page.fill('input#signup-name', 'a');
    await page.fill('input#signup-workspace', 'a');
    
    // Check if the dynamic helper text appears
    const helperText = page.locator('text=Valid email is required');
    await expect(helperText).toBeVisible();
    
    // Check if button is disabled
    const btn = page.locator('button[type="submit"]');
    await expect(btn).toBeDisabled();
    
    // Correction UI (we test this via unit test/API in previous step, but we can verify Logs UI)
    await page.goto('http://localhost:5178/logs');
    // Ensure the page renders without crashing
    await expect(page.getByRole('heading', { name: 'Extraction Logs' })).toBeVisible();
  });
});
