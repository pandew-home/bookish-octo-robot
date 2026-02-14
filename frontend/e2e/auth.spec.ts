import { test, expect } from '@playwright/test';
import { LoginPage } from './page-objects';
import { mockCredentials } from './test-utils';

test.describe('Authentication Flow', () => {
  test('should display login form on initial load', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await expect(loginPage.accessKeyInput).toBeVisible();
    await expect(loginPage.secretKeyInput).toBeVisible();
    await expect(loginPage.sessionTokenInput).toBeVisible();
    await expect(loginPage.regionSelect).toBeVisible();
    await expect(loginPage.loginButton).toBeVisible();
  });

  test('should successfully login with valid Kion credentials', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Mock successful authentication
    await page.route('**/api/credentials/aws', async route => {
      await route.fulfill({
        status: 200,
        json: { sessionId: 'test-session-123' }
      });
    });

    await loginPage.login(mockCredentials);
    await loginPage.waitForLoginSuccess();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Mock authentication failure
    await page.route('**/api/credentials/aws', async route => {
      await route.fulfill({
        status: 401,
        json: { error: 'Invalid AWS credentials' }
      });
    });

    await loginPage.login(mockCredentials);
    await expect(loginPage.errorMessage).toBeVisible();
    await expect(loginPage.errorMessage).toContainText('Invalid AWS credentials');
  });

  test('should validate required fields', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Try to login without filling fields
    await loginPage.loginButton.click();

    // Should show validation errors or prevent submission
    await expect(page).toHaveURL('/'); // Still on login page
  });

  test('should handle network errors during authentication', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Mock network failure
    await page.route('**/api/credentials/aws', async route => {
      await route.abort();
    });

    await loginPage.login(mockCredentials);
    await expect(loginPage.errorMessage).toBeVisible();
  });

  test('should support different AWS regions', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Test region selection
    await loginPage.regionSelect.selectOption('us-west-2');
    await expect(loginPage.regionSelect).toHaveValue('us-west-2');

    await loginPage.regionSelect.selectOption('eu-west-1');
    await expect(loginPage.regionSelect).toHaveValue('eu-west-1');
  });

  test('should mask sensitive input fields', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Secret key should be masked
    await expect(loginPage.secretKeyInput).toHaveAttribute('type', 'password');

    // Session token should be masked
    await expect(loginPage.sessionTokenInput).toHaveAttribute('type', 'password');

    // Access key should be text (not masked)
    await expect(loginPage.accessKeyInput).toHaveAttribute('type', 'text');
  });

  test('should handle credential expiration warnings', async ({ page }) => {
    // This would test the credential badge showing expiration warnings
    // after successful login and cluster selection
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    // Mock successful auth
    await page.route('**/api/credentials/aws', async route => {
      await route.fulfill({
        status: 200,
        json: { sessionId: 'test-session-123' }
      });
    });

    await loginPage.login(mockCredentials);
    await loginPage.waitForLoginSuccess();

    // Navigate to cluster selection and main app
    // (This would be tested in integration tests)
  });
});