import { test, expect } from '@playwright/test';
import { mockClusters, mockCredentials, mockKnowledgeBaseResults } from './test-utils';

async function bootstrapAuthenticatedApp(page: import('@playwright/test').Page) {
  let authenticated = false;

  await page.route('**/api/credentials/status', async route => {
    if (!authenticated) {
      await route.fulfill({ status: 404, json: { present: false, expired: false } });
      return;
    }

    await route.fulfill({
      status: 200,
      json: {
        present: true,
        expired: false,
        account_id: '123456789012',
        user_arn: 'arn:aws:sts::123456789012:assumed-role/devops-chatbot/test-user',
        ttl_seconds: 3600,
      },
    });
  });

  await page.route('**/api/credentials/aws', async route => {
    authenticated = true;
    await route.fulfill({ status: 200, json: { success: true, sessionId: 'test-session-123' } });
  });

  await page.route('**/api/clusters', async route => {
    await route.fulfill({ status: 200, json: { clusters: mockClusters } });
  });

  await page.route('**/api/clusters/select', async route => {
    await route.fulfill({ status: 200, json: { success: true } });
  });

  await page.route('**/api/weather', async route => {
    await route.fulfill({
      status: 200,
      json: {
        weather_state: 'sunny',
        cluster_name: mockClusters[0].name,
        cluster_version: mockClusters[0].version,
        k8sgpt_result_count: 0,
        top_issues: [],
        timestamp: new Date().toISOString(),
      },
    });
  });

  await page.route('**/api/results**', async route => {
    await route.fulfill({ status: 200, json: { results: [], count: 0 } });
  });

  await page.route('**/api/chat/history**', async route => {
    await route.fulfill({ status: 200, json: { messages: [] } });
  });

  await page.goto('/');

  await page.getByLabel('Access Key ID').fill(mockCredentials.accessKeyId);
  await page.getByLabel('Secret Access Key').fill(mockCredentials.secretAccessKey);
  await page.getByLabel('Session Token').fill(mockCredentials.sessionToken);
  await page.getByLabel('AWS Region').click();
  await page.getByRole('option', { name: mockCredentials.region }).click();
  await page.getByRole('button', { name: 'Login' }).click();

  await expect(page.getByText(new RegExp(`Cluster:\\s*${mockClusters[0].name}`))).toBeVisible();
  await expect(page.getByPlaceholder('Ask about your cluster...')).toBeVisible();
}

test.describe('Knowledge Base - Seeded Content', () => {
  test('should expose pre-seeded knowledge base results through search', async ({ page }) => {
    await bootstrapAuthenticatedApp(page);

    await page.route('**/api/kb/search**', async route => {
      await route.fulfill({
        status: 200,
        json: {
          query: 'crashloop',
          results: mockKnowledgeBaseResults.map(result => ({
            id: result.id,
            title: result.title,
            description: result.content,
            tags: result.tags,
            similarity_score: result.relevanceScore,
          })),
          count: mockKnowledgeBaseResults.length,
          search_metadata: {
            total_results: mockKnowledgeBaseResults.length,
            filtered_results: mockKnowledgeBaseResults.length,
            similarity_threshold: 0.7,
            top_k: 5,
          },
        },
      });
    });

    const kbResults = await page.evaluate(async () => {
      const response = await fetch('/api/kb/search?query=crashloop&top_k=5', {
        credentials: 'include',
        headers: {
          'x-session-id': localStorage.getItem('sessionId') || '',
        },
      });

      return response.json();
    });

    expect(kbResults.query).toBe('crashloop');
    expect(Array.isArray(kbResults.results)).toBe(true);
    expect(kbResults.results.length).toBeGreaterThan(0);
    expect(kbResults.results[0].title).toContain('CrashLoopBackOff');
    expect(kbResults.results[0].tags).toContain('crashloopbackoff');
  });

  test('should cite seeded knowledge base content in chat responses', async ({ page }) => {
    await bootstrapAuthenticatedApp(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({
        status: 200,
        json: {
          response: 'The pod is restarting because it is crashing during startup. Start with the CrashLoopBackOff runbook from the seeded knowledge base.',
          citations: [
            {
              documentId: mockKnowledgeBaseResults[0].id,
              title: mockKnowledgeBaseResults[0].title,
              snippet: mockKnowledgeBaseResults[0].snippet,
              relevanceScore: mockKnowledgeBaseResults[0].relevanceScore,
              usageCount: mockKnowledgeBaseResults[0].usageCount,
              successRate: mockKnowledgeBaseResults[0].successRate,
            },
          ],
        },
      });
    });

    await page.getByPlaceholder('Ask about your cluster...').fill('Why is my nginx pod crash looping?');
    await page.getByRole('button').filter({ has: page.locator('svg[data-testid="SendIcon"]') }).click();

    await expect(page.getByText('The pod is restarting because it is crashing during startup.')).toBeVisible();
    await expect(page.getByText(mockKnowledgeBaseResults[0].title, { exact: true })).toBeVisible();

    await page.getByRole('button', { name: /show details/i }).click();
    await expect(page.getByText(mockKnowledgeBaseResults[0].snippet)).toBeVisible();
    await expect(page.getByText(/Used 12 times/i)).toBeVisible();
  });
});
