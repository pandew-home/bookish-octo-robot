import { expect, Page } from '@playwright/test';
import { mockClusters, mockCredentials, mockWeatherData } from './test-utils';

export interface AuthenticatedAppOptions {
  clusterName?: string;
  weatherResponse?: Record<string, unknown>;
  resultsResponse?: unknown[];
  historyMessages?: unknown[];
  credentialStatus?: {
    present: boolean;
    expired: boolean;
    account_id?: string;
    user_arn?: string;
    ttl_seconds?: number;
    expires_at?: string;
  };
  onChatRequest?: (body: any) => Record<string, unknown>;
  onSelectCluster?: (body: any) => { status?: number; json: Record<string, unknown> };
}

const defaultCredentialStatus = {
  present: true,
  expired: false,
  account_id: '123456789012',
  user_arn: 'arn:aws:sts::123456789012:assumed-role/devops-chatbot/test-user',
  ttl_seconds: 3600,
};

export async function mockAuthenticatedApp(page: Page, options: AuthenticatedAppOptions = {}) {
  const clusterName = options.clusterName ?? mockClusters[0].name;
  let authenticated = false;

  await page.route('**/api/credentials/status', async route => {
    if (!authenticated) {
      await route.fulfill({ status: 404, json: { present: false, expired: false } });
      return;
    }

    await route.fulfill({
      status: 200,
      json: options.credentialStatus ?? defaultCredentialStatus,
    });
  });

  await page.route('**/api/credentials/aws', async route => {
    authenticated = true;
    await route.fulfill({
      status: 200,
      json: { success: true, sessionId: 'test-session-123' },
    });
  });

  await page.route('**/api/clusters', async route => {
    await route.fulfill({
      status: 200,
      json: { clusters: mockClusters },
    });
  });

  await page.route('**/api/clusters/select', async route => {
    const body = route.request().postDataJSON?.() ?? {};

    if (options.onSelectCluster) {
      const response = options.onSelectCluster(body);
      await route.fulfill({ status: response.status ?? 200, json: response.json });
      return;
    }

    await route.fulfill({ status: 200, json: { success: true } });
  });

  await page.route('**/api/weather', async route => {
    await route.fulfill({
      status: 200,
      json: options.weatherResponse ?? buildWeatherResponse(clusterName, mockWeatherData.sunny),
    });
  });

  await page.route('**/api/results**', async route => {
    await route.fulfill({
      status: 200,
      json: { results: options.resultsResponse ?? [], count: (options.resultsResponse ?? []).length },
    });
  });

  await page.route('**/api/chat/history**', async route => {
    await route.fulfill({
      status: 200,
      json: { messages: options.historyMessages ?? [] },
    });
  });

  await page.route('**/api/chat/export', async route => {
    await route.fulfill({
      status: 200,
      json: {
        cluster: clusterName,
        timestamp: new Date().toISOString(),
        problem: 'Problem summary',
        investigation: 'Investigation summary',
        rootCause: 'Root cause summary',
        solution: 'Solution summary',
        verification: 'Verification summary',
      },
    });
  });

  await page.route('**/api/chat', async route => {
    const body = route.request().postDataJSON?.() ?? {};
    const response = options.onChatRequest?.(body) ?? {
      response: 'Default assistant response',
      query_type: 'general_k8s',
      citations: [],
    };
    await route.fulfill({ status: 200, json: response });
  });

  await page.goto('/');

  await page.getByLabel('Access Key ID').fill(mockCredentials.accessKeyId);
  await page.getByLabel('Secret Access Key').fill(mockCredentials.secretAccessKey);
  await page.getByLabel('Session Token').fill(mockCredentials.sessionToken);
  await page.getByRole('button', { name: 'Login' }).click();

  await expect(page.getByText(new RegExp(`Cluster:\\s*${clusterName}`))).toBeVisible();
  await expect(page.getByPlaceholder('Ask about your cluster...')).toBeVisible();
}

function buildWeatherResponse(clusterName: string, weather: typeof mockWeatherData.sunny) {
  return {
    weather_state: weather.state,
    cluster_name: clusterName,
    cluster_version: weather.clusterVersion,
    k8sgpt_result_count: weather.k8sgptResultCount,
    top_issues: weather.topIssues,
    timestamp: weather.timestamp,
    k8sgpt_status: 'available',
  };
}
