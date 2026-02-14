import { test, expect } from '@playwright/test';
import { LoginPage, ClusterPage, ChatInterface } from './page-objects';
import { mockCredentials, mockClusters, mockChatResponses, clusterFailureScenarios } from './test-utils';

test.describe('Chat Interface - Troubleshooting Queries', () => {
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

  test('should send chat message and receive response', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: mockChatResponses.podIssue });
    });

    await chatInterface.sendMessage('Why is my nginx pod crashing?');

    const lastMessage = await chatInterface.getLastAssistantMessage();
    expect(lastMessage).toContain('CrashLoopBackOff');
    expect(lastMessage).toContain('nginx pod');
  });

  test('should display citations when available', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: mockChatResponses.podIssue });
    });

    await chatInterface.sendMessage('nginx pod issue');

    const hasCitations = await chatInterface.hasCitations();
    expect(hasCitations).toBe(true);

    await expect(page.locator('[data-testid="citation"]')).toContainText('Troubleshooting CrashLoopBackOff');
  });

  test('should display K8sGPT findings prominently', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: mockChatResponses.podIssue });
    });

    await chatInterface.sendMessage('pod crash issue');

    const hasFindings = await chatInterface.hasK8sGPTFindings();
    expect(hasFindings).toBe(true);

    await expect(page.locator('[data-testid="k8sgpt-finding"]')).toContainText('CrashLoopBackOff');
    await expect(page.locator('[data-testid="k8sgpt-finding"]')).toContainText('pod-crashloopbackoff');
  });

  test('should show safety notices for destructive recommendations', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    const responseWithSafetyNotice = {
      ...mockChatResponses.podIssue,
      safetyNotice: 'Warning: This action may cause service disruption'
    };

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: responseWithSafetyNotice });
    });

    await chatInterface.sendMessage('delete problematic pod');

    const hasSafetyNotice = await chatInterface.hasSafetyNotice();
    expect(hasSafetyNotice).toBe(true);

    await expect(page.locator('[data-testid="safety-notice"]')).toContainText('service disruption');
  });

  test('should handle pod crash troubleshooting', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: mockChatResponses.podIssue });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.podCrashLoop.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.podCrashLoop.expectedResponse);
  });

  test('should handle deployment unavailable issues', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: mockChatResponses.deploymentIssue });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.deploymentUnavailable.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.deploymentUnavailable.expectedResponse);
  });

  test('should handle network connectivity issues', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    const networkResponse = {
      id: 'msg-network',
      role: 'assistant',
      content: 'The service is experiencing timeout issues. This could be due to network policies or DNS resolution problems.',
      k8sgptFindings: [{
        name: 'service-timeout',
        kind: 'Service',
        namespace: 'default',
        severity: 'medium',
        problem: 'Service nginx-service has timeout errors'
      }],
      timestamp: new Date().toISOString()
    };

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: networkResponse });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.networkTimeout.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.networkTimeout.expectedResponse);
  });

  test('should handle storage issues', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    const storageResponse = {
      id: 'msg-storage',
      role: 'assistant',
      content: 'The persistent volume is full. This requires immediate attention to prevent data loss.',
      k8sgptFindings: [{
        name: 'pvc-full',
        kind: 'PersistentVolumeClaim',
        namespace: 'default',
        severity: 'high',
        problem: 'PVC data-pvc is 100% full'
      }],
      safetyNotice: 'Critical: Data loss may occur if not addressed immediately',
      timestamp: new Date().toISOString()
    };

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: storageResponse });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.storageFull.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.storageFull.expectedResponse);

    const hasSafetyNotice = await chatInterface.hasSafetyNotice();
    expect(hasSafetyNotice).toBe(true);
  });

  test('should handle RBAC permission issues', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    const rbacResponse = {
      id: 'msg-rbac',
      role: 'assistant',
      content: 'Access is denied due to RBAC permissions. The service account lacks required permissions.',
      k8sgptFindings: [{
        name: 'rbac-denied',
        kind: 'ServiceAccount',
        namespace: 'default',
        severity: 'medium',
        problem: 'ServiceAccount default-sa denied access to secrets'
      }],
      timestamp: new Date().toISOString()
    };

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: rbacResponse });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.rbacForbidden.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.rbacForbidden.expectedResponse);
  });

  test('should handle node health issues', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    const nodeResponse = {
      id: 'msg-node',
      role: 'assistant',
      content: 'The node is not ready. This affects all pods scheduled on this node.',
      k8sgptFindings: [{
        name: 'node-notready',
        kind: 'Node',
        namespace: '',
        severity: 'high',
        problem: 'Node ip-10-0-1-123 is NotReady'
      }],
      timestamp: new Date().toISOString()
    };

    await page.route('**/api/chat', async route => {
      await route.fulfill({ status: 200, json: nodeResponse });
    });

    await chatInterface.sendMessage(clusterFailureScenarios.nodeNotReady.query);

    const response = await chatInterface.getLastAssistantMessage();
    expect(response).toMatch(clusterFailureScenarios.nodeNotReady.expectedResponse);
  });

  test('should reject unsafe queries', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    // Mock input sanitizer rejection
    await page.route('**/api/chat', async route => {
      await route.fulfill({
        status: 400,
        json: { error: 'Query contains unsafe patterns' }
      });
    });

    await chatInterface.sendMessage('kubectl delete all --all');

    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-message"]')).toContainText('unsafe patterns');
  });

  test('should handle rate limiting', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({
        status: 429,
        json: { error: 'Rate limit exceeded' },
        headers: { 'Retry-After': '60' }
      });
    });

    await chatInterface.sendMessage('test query');

    await expect(page.locator('[data-testid="rate-limit-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="retry-after"]')).toContainText('60');
  });

  test('should handle network errors during chat', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.abort();
    });

    await chatInterface.sendMessage('test query');

    await expect(page.locator('[data-testid="connection-error"]')).toBeVisible();
  });

  test('should maintain conversation history', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    // Mock multiple responses
    let callCount = 0;
    await page.route('**/api/chat', async route => {
      callCount++;
      const responses = [mockChatResponses.podIssue, mockChatResponses.deploymentIssue];
      await route.fulfill({ status: 200, json: responses[callCount - 1] });
    });

    await chatInterface.sendMessage('First question');
    await chatInterface.sendMessage('Follow up question');

    const messageCount = await chatInterface.getMessageCount();
    expect(messageCount).toBe(4); // 2 user + 2 assistant messages
  });

  test('should show typing indicator while processing', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    // Delay response to show loading state
    await page.route('**/api/chat', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.fulfill({ status: 200, json: mockChatResponses.podIssue });
    });

    await chatInterface.sendMessage('test query');

    await expect(page.locator('[data-testid="typing-indicator"]')).toBeVisible();

    // Wait for response
    await page.locator('[data-testid="assistant-message"]').waitFor();
    await expect(page.locator('[data-testid="typing-indicator"]')).not.toBeVisible();
  });

  test('should handle empty responses gracefully', async ({ page }) => {
    const chatInterface = new ChatInterface(page);

    await page.route('**/api/chat', async route => {
      await route.fulfill({
        status: 200,
        json: { id: 'msg-empty', role: 'assistant', content: '', timestamp: new Date().toISOString() }
      });
    });

    await chatInterface.sendMessage('test query');

    // Should handle empty response without crashing
    const messageCount = await chatInterface.getMessageCount();
    expect(messageCount).toBe(2); // user + assistant (even if empty)
  });
});