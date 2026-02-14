import { test, expect } from '@playwright/test';
import { LoginPage, ClusterPage, MainAppPage, ChatInterface } from './page-objects';
import { mockCredentials, mockClusters, simulateNetworkError, simulateAuthError, simulateClusterUnavailable } from './test-utils';

test.describe('Error Scenarios and Cluster Failures', () => {
  test.describe('Network and Connectivity Issues', () => {
    test('should handle complete network failure', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      // Simulate network failure
      simulateNetworkError(page);

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
      await expect(loginPage.errorMessage).toContainText('network');
    });

    test('should handle intermittent network issues during chat', async ({ page }) => {
      // Setup authenticated session
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);
      const chatInterface = new ChatInterface(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({ status: 200, json: { success: true } });
      });

      await clusterPage.selectCluster('dev-cluster-01');
      await clusterPage.waitForMainApp();

      // Simulate network failure during chat
      let callCount = 0;
      await page.route('**/api/chat', async route => {
        callCount++;
        if (callCount === 1) {
          await route.abort(); // First call fails
        } else {
          await route.fulfill({
            status: 200,
            json: {
              id: 'msg-retry',
              role: 'assistant',
              content: 'Response after retry',
              timestamp: new Date().toISOString()
            }
          });
        }
      });

      await chatInterface.sendMessage('test query');

      // Should show error then retry successfully
      await expect(page.locator('[data-testid="connection-error"]')).toBeVisible();

      // Wait for retry
      await page.waitForTimeout(2000);
      await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible();
    });

    test('should handle DNS resolution failures', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      // Mock DNS failure
      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({
          status: 0, // Network error
          body: 'DNS resolution failed'
        });
      });

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
    });
  });

  test.describe('Authentication Failures', () => {
    test('should handle expired Kion credentials', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({
          status: 401,
          json: { error: 'AWS credentials have expired' }
        });
      });

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
      await expect(loginPage.errorMessage).toContainText('expired');
    });

    test('should handle invalid session tokens', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({
          status: 401,
          json: { error: 'Invalid session token' }
        });
      });

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
      await expect(loginPage.errorMessage).toContainText('session token');
    });

    test('should handle insufficient AWS permissions', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({
          status: 403,
          json: { error: 'Access denied: insufficient permissions' }
        });
      });

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
      await expect(loginPage.errorMessage).toContainText('permissions');
    });

    test('should handle session timeout during usage', async ({ page }) => {
      // Setup authenticated session
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);
      const mainAppPage = new MainAppPage(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({ status: 200, json: { success: true } });
      });

      await clusterPage.selectCluster('dev-cluster-01');
      await clusterPage.waitForMainApp();

      // Simulate session expiration during weather polling
      await page.route('**/api/weather', async route => {
        await route.fulfill({
          status: 401,
          json: { error: 'Session expired' }
        });
      });

      await page.waitForTimeout(100); // Allow weather polling

      // Should show session expired message
      await expect(page.locator('[data-testid="session-expired"]')).toBeVisible();
    });
  });

  test.describe('Cluster Connectivity Issues', () => {
    test.beforeEach(async ({ page }) => {
      // Setup authenticated session
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });
    });

    test('should handle unreachable EKS clusters', async ({ page }) => {
      const clusterPage = new ClusterPage(page);

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({
          status: 503,
          json: { error: 'Cluster endpoint unreachable' }
        });
      });

      await clusterPage.selectCluster('dev-cluster-01');

      await expect(clusterPage.errorMessage).toBeVisible();
      await expect(clusterPage.errorMessage).toContainText('unreachable');
    });

    test('should handle RBAC permission denied for cluster access', async ({ page }) => {
      const clusterPage = new ClusterPage(page);

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({
          status: 403,
          json: { error: 'RBAC: access denied to cluster' }
        });
      });

      await clusterPage.selectCluster('prod-cluster-01');

      await expect(clusterPage.errorMessage).toBeVisible();
      await expect(clusterPage.errorMessage).toContainText('RBAC');
    });

    test('should handle cluster certificate validation failures', async ({ page }) => {
      const clusterPage = new ClusterPage(page);

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({
          status: 500,
          json: { error: 'SSL certificate validation failed' }
        });
      });

      await clusterPage.selectCluster('dev-cluster-01');

      await expect(clusterPage.errorMessage).toBeVisible();
      await expect(clusterPage.errorMessage).toContainText('certificate');
    });

    test('should handle cluster API server timeouts', async ({ page }) => {
      const clusterPage = new ClusterPage(page);

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({
          status: 504,
          json: { error: 'Cluster API server timeout' }
        });
      });

      await clusterPage.selectCluster('dev-cluster-01');

      await expect(clusterPage.errorMessage).toBeVisible();
      await expect(clusterPage.errorMessage).toContainText('timeout');
    });
  });

  test.describe('K8sGPT Operator Issues', () => {
    test.beforeEach(async ({ page }) => {
      // Setup authenticated session with cluster selected
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({ status: 200, json: { success: true } });
      });

      await clusterPage.selectCluster('dev-cluster-01');
      await clusterPage.waitForMainApp();
    });

    test('should handle K8sGPT operator not installed', async ({ page }) => {
      await page.route('**/api/weather', async route => {
        await route.fulfill({
          status: 200,
          json: {
            state: 'sunny',
            clusterName: 'dev-cluster-01',
            clusterVersion: '1.28.0',
            k8sgptResultCount: 0,
            topIssues: [],
            clusterTools: [{
              name: 'k8sgpt',
              version: 'N/A',
              category: 'diagnostics',
              status: 'unknown'
            }],
            k8sgptStatus: 'not_installed',
            k8sgptMessage: 'K8sGPT operator not found in cluster',
            timestamp: new Date().toISOString()
          }
        });
      });

      await page.waitForTimeout(100);

      await expect(page.locator('[data-testid="k8sgpt-warning"]')).toBeVisible();
      await expect(page.locator('[data-testid="k8sgpt-warning"]')).toContainText('not found');
    });

    test('should handle K8sGPT operator unreachable', async ({ page }) => {
      await page.route('**/api/weather', async route => {
        await route.fulfill({
          status: 200,
          json: {
            state: 'cloudy',
            clusterName: 'dev-cluster-01',
            clusterVersion: '1.28.0',
            k8sgptResultCount: 0,
            topIssues: [],
            clusterTools: [{
              name: 'k8sgpt',
              version: 'v0.3.0',
              category: 'diagnostics',
              status: 'unknown'
            }],
            k8sgptStatus: 'unreachable',
            k8sgptMessage: 'Cannot connect to K8sGPT operator',
            timestamp: new Date().toISOString()
          }
        });
      });

      await page.waitForTimeout(100);

      await expect(page.locator('[data-testid="k8sgpt-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="k8sgpt-error"]')).toContainText('connect');
    });

    test('should handle corrupted K8sGPT results', async ({ page }) => {
      const chatInterface = new ChatInterface(page);

      await page.route('**/api/chat', async route => {
        await route.fulfill({
          status: 200,
          json: {
            id: 'msg-corrupted',
            role: 'assistant',
            content: 'Unable to parse K8sGPT results due to corruption',
            errorType: 'cluster_unreachable',
            timestamp: new Date().toISOString()
          }
        });
      });

      await chatInterface.sendMessage('check cluster health');

      await expect(page.locator('[data-testid="cluster-error"]')).toBeVisible();
    });
  });

  test.describe('Resource Exhaustion Scenarios', () => {
    test('should handle memory exhaustion in browser', async ({ page }) => {
      // This test would be difficult to simulate reliably
      // Instead, we test graceful handling of large responses
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);
      const chatInterface = new ChatInterface(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({ status: 200, json: { success: true } });
      });

      await clusterPage.selectCluster('dev-cluster-01');
      await clusterPage.waitForMainApp();

      // Simulate very large response that might cause memory issues
      const largeResponse = {
        id: 'msg-large',
        role: 'assistant',
        content: 'x'.repeat(100000), // 100KB response
        timestamp: new Date().toISOString()
      };

      await page.route('**/api/chat', async route => {
        await route.fulfill({ status: 200, json: largeResponse });
      });

      await chatInterface.sendMessage('large query');

      // Should handle large response without crashing
      await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible();
    });

    test('should handle API rate limiting', async ({ page }) => {
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);
      const chatInterface = new ChatInterface(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      await page.route('**/api/clusters', async route => {
        await route.fulfill({ status: 200, json: mockClusters });
      });

      await page.route('**/api/clusters/select', async route => {
        await route.fulfill({ status: 200, json: { success: true } });
      });

      await clusterPage.selectCluster('dev-cluster-01');
      await clusterPage.waitForMainApp();

      // Simulate rate limiting
      await page.route('**/api/chat', async route => {
        await route.fulfill({
          status: 429,
          json: { error: 'Rate limit exceeded' },
          headers: { 'Retry-After': '30' }
        });
      });

      await chatInterface.sendMessage('rate limited query');

      await expect(page.locator('[data-testid="rate-limit-message"]')).toBeVisible();
      await expect(page.locator('[data-testid="retry-after"]')).toContainText('30');
    });
  });

  test.describe('Data Corruption and Validation', () => {
    test('should handle malformed JSON responses', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: '{ invalid json }'
        });
      });

      await loginPage.login(mockCredentials);

      await expect(loginPage.errorMessage).toBeVisible();
    });

    test('should handle unexpected response formats', async ({ page }) => {
      const loginPage = new LoginPage(page);
      const clusterPage = new ClusterPage(page);

      await loginPage.goto();

      await page.route('**/api/credentials/aws', async route => {
        await route.fulfill({ status: 200, json: { sessionId: 'test-session-123' } });
      });

      await loginPage.login(mockCredentials);
      await loginPage.waitForLoginSuccess();

      // Return HTML instead of JSON
      await page.route('**/api/clusters', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/html',
          body: '<html><body>Unexpected HTML response</body></html>'
        });
      });

      // Should handle gracefully
      await expect(clusterPage.errorMessage).toBeVisible();
    });
  });
});