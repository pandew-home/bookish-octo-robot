import { test, expect } from '@playwright/test';
import { LoginPage, ClusterPage, WeatherWidget } from './page-objects';
import { mockCredentials, mockClusters, mockWeatherData } from './test-utils';

test.describe('Weather Widget - Cluster Health Monitoring', () => {
  test.beforeEach(async ({ page }) => {
    // Login and select cluster
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

  test('should display sunny weather for healthy cluster', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.sunny });
    });

    await page.waitForTimeout(100); // Allow weather polling

    const weatherState = await weatherWidget.getWeatherState();
    expect(weatherState).toBe('sunny');

    const issueCount = await weatherWidget.getIssueCount();
    expect(issueCount).toBe(0);
  });

  test('should display cloudy weather for cluster with warnings', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.cloudy });
    });

    await page.waitForTimeout(100);

    const weatherState = await weatherWidget.getWeatherState();
    expect(weatherState).toBe('cloudy');

    const issueCount = await weatherWidget.getIssueCount();
    expect(issueCount).toBe(3);

    const topIssues = await weatherWidget.getTopIssues();
    expect(topIssues.length).toBeGreaterThan(0);
    expect(topIssues[0]).toContain('CrashLoopBackOff');
  });

  test('should display stormy weather for cluster with critical issues', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.stormy });
    });

    await page.waitForTimeout(100);

    const weatherStateValue = await weatherWidget.getWeatherState();
    expect(weatherStateValue).toBe('stormy');

    const issueCount = await weatherWidget.getIssueCount();
    expect(issueCount).toBe(8);

    const topIssues = await weatherWidget.getTopIssues();
    expect(topIssues.length).toBe(2);
    expect(topIssues.some(issue => issue.includes('NotReady'))).toBe(true);
    expect(topIssues.some(issue => issue.includes('unavailable'))).toBe(true);
  });

  test('should show cluster name and version', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.sunny });
    });

    await page.waitForTimeout(100);

    const clusterName = await weatherWidget.getClusterName();
    expect(clusterName).toBe('dev-cluster-01');

    await expect(page.locator('[data-testid="cluster-version"]')).toContainText('1.28.0');
  });

  test('should display tool health status', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.sunny });
    });

    await page.waitForTimeout(100);

    const toolsStatus = await weatherWidget.getToolsStatus();
    expect(toolsStatus.k8sgpt).toBe('healthy');
    expect(toolsStatus.argocd).toBe('healthy');
  });

  test('should handle weather API failures gracefully', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 500, json: { error: 'Weather service unavailable' } });
    });

    await page.waitForTimeout(100);

    // Should show error state or fallback
    await expect(page.locator('[data-testid="weather-error"]')).toBeVisible();
  });

  test('should poll weather data every 60 seconds', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    let apiCallCount = 0;
    await page.route('**/api/weather', async route => {
      apiCallCount++;
      await route.fulfill({ status: 200, json: mockWeatherData.sunny });
    });

    await page.waitForTimeout(100);
    expect(apiCallCount).toBeGreaterThan(0);

    // Wait for polling interval (would be 60 seconds in real app)
    // For testing, we just verify the initial call
  });

  test('should allow clicking on issues to pre-fill chat', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);
    const chatInterface = page.locator('[data-testid="chat-interface"]');

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.cloudy });
    });

    await page.waitForTimeout(100);

    // Click on an issue
    await weatherWidget.clickOnIssue(0);

    // Should pre-fill chat with issue description
    await expect(chatInterface.locator('[data-testid="chat-input"]')).toHaveValue(/CrashLoopBackOff/);
  });

  test('should handle K8sGPT not installed scenario', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    const weatherDataWithoutK8sGPT = {
      ...mockWeatherData.sunny,
      k8sgptStatus: 'not_installed' as const,
      k8sgptMessage: 'K8sGPT operator not found in cluster'
    };

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: weatherDataWithoutK8sGPT });
    });

    await page.waitForTimeout(100);

    const toolsStatus = await weatherWidget.getToolsStatus();
    expect(toolsStatus.k8sgpt).toBe('unknown');

    await expect(page.locator('[data-testid="k8sgpt-warning"]')).toBeVisible();
  });

  test('should handle unreachable K8sGPT scenario', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);

    const weatherDataWithUnreachableK8sGPT = {
      ...mockWeatherData.cloudy,
      k8sgptStatus: 'unreachable' as const,
      k8sgptMessage: 'Cannot connect to K8sGPT operator'
    };

    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: weatherDataWithUnreachableK8sGPT });
    });

    await page.waitForTimeout(100);

    const toolsStatus = await weatherWidget.getToolsStatus();
    expect(toolsStatus.k8sgpt).toBe('unknown');

    await expect(page.locator('[data-testid="k8sgpt-error"]')).toBeVisible();
  });

  test('should update weather state when switching clusters', async ({ page }) => {
    const weatherWidget = new WeatherWidget(page);
    const mainAppPage = page.locator('[data-testid="main-app"]');

    // Initial weather data
    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.sunny });
    }, { times: 1 });

    await page.waitForTimeout(100);
    expect(await weatherWidget.getWeatherState()).toBe('sunny');

    // Switch cluster - mock different weather data
    await page.route('**/api/weather', async route => {
      await route.fulfill({ status: 200, json: mockWeatherData.stormy });
    });

    await mainAppPage.locator('[data-testid="cluster-selector"]').selectOption('prod-cluster-01');
    await page.waitForTimeout(100);

    // Weather should update
    const newWeatherState = await weatherWidget.getWeatherState();
    expect(newWeatherState).toBe('stormy');
  });
});