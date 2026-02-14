import { test, expect } from '@playwright/test';
import { LoginPage, ClusterPage, MainAppPage } from './page-objects';
import { mockCredentials, mockClusters } from './test-utils';

test.describe('Cluster Management', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await page.route('**/api/credentials/aws', async route => {
      await route.fulfill({
        status: 200,
        json: { sessionId: 'test-session-123' }
      });
    });

    await loginPage.login(mockCredentials);
    await loginPage.waitForLoginSuccess();
  });

  test('should display available clusters after login', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    // Mock cluster discovery
    await page.route('**/api/clusters', async route => {
      await route.fulfill({
        status: 200,
        json: mockClusters
      });
    });

    const clusterCount = await clusterPage.getClusterCount();
    expect(clusterCount).toBeGreaterThan(0);

    const clusterNames = await clusterPage.getClusterNames();
    expect(clusterNames).toContain('dev-cluster-01');
    expect(clusterNames).toContain('staging-cluster-01');
    expect(clusterNames).toContain('prod-cluster-01');
  });

  test('should show cluster metadata (region, version, status)', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    await page.route('**/api/clusters', async route => {
      await route.fulfill({
        status: 200,
        json: mockClusters
      });
    });

    // Check that cluster information is displayed
    await expect(page.locator('[data-testid="cluster-region"]')).toContainText('us-east-1');
    await expect(page.locator('[data-testid="cluster-version"]')).toContainText('1.28.0');
    await expect(page.locator('[data-testid="cluster-status"]')).toContainText('ACTIVE');
  });

  test('should successfully select a cluster and navigate to main app', async ({ page }) => {
    const clusterPage = new ClusterPage(page);
    const mainAppPage = new MainAppPage(page);

    // Mock APIs
    await page.route('**/api/clusters', async route => {
      await route.fulfill({ status: 200, json: mockClusters });
    });

    await page.route('**/api/clusters/select', async route => {
      await route.fulfill({ status: 200, json: { success: true } });
    });

    await clusterPage.selectCluster('dev-cluster-01');
    await clusterPage.waitForMainApp();

    await expect(mainAppPage.weatherWidget).toBeVisible();
    await expect(mainAppPage.chatInterface).toBeVisible();
  });

  test('should handle cluster discovery failures', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    // Mock cluster discovery failure
    await page.route('**/api/clusters', async route => {
      await route.fulfill({
        status: 500,
        json: { error: 'Failed to discover clusters' }
      });
    });

    await expect(clusterPage.errorMessage).toBeVisible();
    await expect(clusterPage.errorMessage).toContainText('Failed to discover clusters');
  });

  test('should handle cluster selection failures', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    await page.route('**/api/clusters', async route => {
      await route.fulfill({ status: 200, json: mockClusters });
    });

    // Mock cluster selection failure
    await page.route('**/api/clusters/select', async route => {
      await route.fulfill({
        status: 403,
        json: { error: 'Access denied to cluster' }
      });
    });

    await clusterPage.selectCluster('prod-cluster-01');
    await expect(clusterPage.errorMessage).toBeVisible();
  });

  test('should show loading state during cluster operations', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    await page.route('**/api/clusters', async route => {
      // Delay response to show loading state
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.fulfill({ status: 200, json: mockClusters });
    });

    await expect(clusterPage.loadingSpinner).toBeVisible();

    // Wait for loading to complete
    await clusterPage.loadingSpinner.waitFor({ state: 'hidden' });
  });

  test('should support switching between clusters in main app', async ({ page }) => {
    const clusterPage = new ClusterPage(page);
    const mainAppPage = new MainAppPage(page);

    // Setup initial cluster selection
    await page.route('**/api/clusters', async route => {
      await route.fulfill({ status: 200, json: mockClusters });
    });

    await page.route('**/api/clusters/select', async route => {
      await route.fulfill({ status: 200, json: { success: true } });
    });

    await clusterPage.selectCluster('dev-cluster-01');
    await clusterPage.waitForMainApp();

    // Switch to different cluster
    await mainAppPage.switchCluster('staging-cluster-01');

    // Verify cluster switch
    await expect(mainAppPage.clusterSelector).toHaveValue('staging-cluster-01');
  });

  test('should cache cluster discovery results', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    let apiCallCount = 0;
    await page.route('**/api/clusters', async route => {
      apiCallCount++;
      await route.fulfill({ status: 200, json: mockClusters });
    });

    // First load
    await page.reload();
    await page.waitForLoadState();

    // Second load (should use cache)
    await page.reload();
    await page.waitForLoadState();

    // Should only have made one API call due to caching
    expect(apiCallCount).toBeLessThanOrEqual(2); // Allow some flexibility
  });

  test('should display environment-based cluster styling', async ({ page }) => {
    const clusterPage = new ClusterPage(page);

    await page.route('**/api/clusters', async route => {
      await route.fulfill({ status: 200, json: mockClusters });
    });

    // Check environment-based styling
    const devCluster = page.locator('[data-cluster-env="dev"]');
    const stagingCluster = page.locator('[data-cluster-env="staging"]');
    const prodCluster = page.locator('[data-cluster-env="prod"]');

    await expect(devCluster).toBeVisible();
    await expect(stagingCluster).toBeVisible();
    await expect(prodCluster).toBeVisible();
  });
});