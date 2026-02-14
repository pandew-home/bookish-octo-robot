import { Page, APIRequestContext } from '@playwright/test';
import { KionCredentials } from '../src/types/credentials';

/**
 * Test utilities for DevOps Chatbot e2e tests
 */

/**
 * Mock Kion credentials for testing
 */
export const mockCredentials: KionCredentials = {
  accessKeyId: 'AKIATEST123456789012',
  secretAccessKey: 'test-secret-key-for-playwright-testing',
  sessionToken: 'test-session-token-for-playwright-testing',
  region: 'us-east-1'
};

/**
 * Mock cluster data for testing
 */
export const mockClusters = [
  {
    name: 'dev-cluster-01',
    endpoint: 'https://dev-cluster-01.example.com',
    version: '1.28.0',
    status: 'ACTIVE',
    region: 'us-east-1'
  },
  {
    name: 'staging-cluster-01',
    endpoint: 'https://staging-cluster-01.example.com',
    version: '1.28.0',
    status: 'ACTIVE',
    region: 'us-east-1'
  },
  {
    name: 'prod-cluster-01',
    endpoint: 'https://prod-cluster-01.example.com',
    version: '1.27.0',
    status: 'ACTIVE',
    region: 'us-west-2'
  }
];

/**
 * Mock weather data for different cluster states
 */
export const mockWeatherData = {
  sunny: {
    state: 'sunny',
    clusterName: 'dev-cluster-01',
    clusterVersion: '1.28.0',
    k8sgptResultCount: 0,
    topIssues: [],
    clusterTools: [
      { name: 'k8sgpt', version: 'v0.3.0', category: 'diagnostics', status: 'healthy' },
      { name: 'argocd', version: 'v2.7.0', category: 'gitops', status: 'healthy' }
    ],
    timestamp: new Date().toISOString()
  },
  cloudy: {
    state: 'cloudy',
    clusterName: 'staging-cluster-01',
    clusterVersion: '1.28.0',
    k8sgptResultCount: 3,
    topIssues: [
      {
        name: 'pod-crashloopbackoff',
        kind: 'Pod',
        namespace: 'default',
        severity: 'medium',
        problem: 'Pod nginx-deployment-12345 is in CrashLoopBackOff state',
        analyzer: 'podAnalyzer'
      }
    ],
    clusterTools: [
      { name: 'k8sgpt', version: 'v0.3.0', category: 'diagnostics', status: 'healthy' }
    ],
    timestamp: new Date().toISOString()
  },
  stormy: {
    state: 'stormy',
    clusterName: 'prod-cluster-01',
    clusterVersion: '1.27.0',
    k8sgptResultCount: 8,
    topIssues: [
      {
        name: 'node-notready',
        kind: 'Node',
        namespace: '',
        severity: 'high',
        problem: 'Node ip-10-0-1-123 is NotReady',
        analyzer: 'nodeAnalyzer'
      },
      {
        name: 'deployment-unavailable',
        kind: 'Deployment',
        namespace: 'production',
        severity: 'high',
        problem: 'Deployment api-server has 0/3 replicas available',
        analyzer: 'deploymentAnalyzer'
      }
    ],
    clusterTools: [
      { name: 'k8sgpt', version: 'v0.3.0', category: 'diagnostics', status: 'degraded' }
    ],
    timestamp: new Date().toISOString()
  }
};

/**
 * Mock chat responses for different scenarios
 */
export const mockChatResponses = {
  podIssue: {
    id: 'msg-1',
    role: 'assistant',
    content: 'The nginx pod is experiencing CrashLoopBackOff. This typically indicates the container is failing to start properly.',
    citations: [
      {
        documentId: 'kb-001',
        title: 'Troubleshooting CrashLoopBackOff',
        snippet: 'Check pod logs and events for startup failures',
        relevanceScore: 0.95
      }
    ],
    k8sgptFindings: [
      {
        name: 'pod-crashloopbackoff',
        kind: 'Pod',
        namespace: 'default',
        severity: 'medium',
        problem: 'Pod nginx-deployment-12345 is in CrashLoopBackOff state'
      }
    ],
    safetyNotice: 'This diagnosis is based on K8sGPT analysis and may require careful review.',
    timestamp: new Date().toISOString()
  },
  deploymentIssue: {
    id: 'msg-2',
    role: 'assistant',
    content: 'The deployment has unavailable replicas. This could be due to resource constraints or image pull issues.',
    k8sgptFindings: [
      {
        name: 'deployment-unavailable',
        kind: 'Deployment',
        namespace: 'production',
        severity: 'high',
        problem: 'Deployment api-server has 0/3 replicas available'
      }
    ],
    timestamp: new Date().toISOString()
  }
};

/**
 * Setup mock API responses for testing
 */
export async function setupMockAPI(request: APIRequestContext) {
  // Mock credential validation
  await request.post('**/api/credentials/aws', {
    data: mockCredentials
  }).then(() => ({
    status: 200,
    json: { sessionId: 'test-session-123' }
  }));

  // Mock cluster discovery
  await request.get('**/api/clusters').then(() => ({
    status: 200,
    json: mockClusters
  }));

  // Mock cluster selection
  await request.post('**/api/clusters/select', {
    data: { clusterName: 'dev-cluster-01' }
  }).then(() => ({
    status: 200,
    json: { success: true }
  }));

  // Mock weather endpoint
  await request.get('**/api/weather').then(() => ({
    status: 200,
    json: mockWeatherData.sunny
  }));

  // Mock chat endpoint
  await request.post('**/api/chat', {
    data: { query: 'Why is my nginx pod crashing?' }
  }).then(() => ({
    status: 200,
    json: mockChatResponses.podIssue
  }));
}

/**
 * Fill login form with mock credentials
 */
export async function loginWithMockCredentials(page: Page) {
  await page.fill('[data-testid="access-key-input"]', mockCredentials.accessKeyId);
  await page.fill('[data-testid="secret-key-input"]', mockCredentials.secretAccessKey);
  await page.fill('[data-testid="session-token-input"]', mockCredentials.sessionToken);
  await page.selectOption('[data-testid="region-select"]', mockCredentials.region);
  await page.click('[data-testid="login-button"]');
}

/**
 * Wait for main application to load after login
 */
export async function waitForAppLoad(page: Page) {
  await page.waitForSelector('[data-testid="weather-widget"]');
  await page.waitForSelector('[data-testid="chat-interface"]');
}

/**
 * Select a cluster from the cluster selector
 */
export async function selectCluster(page: Page, clusterName: string) {
  await page.selectOption('[data-testid="cluster-selector"]', clusterName);
  await page.waitForSelector(`[data-testid="cluster-${clusterName}"]`);
}

/**
 * Send a chat message and wait for response
 */
export async function sendChatMessage(page: Page, message: string) {
  await page.fill('[data-testid="chat-input"]', message);
  await page.click('[data-testid="send-button"]');
  await page.waitForSelector('[data-testid="assistant-message"]');
}

/**
 * Common test cluster failure scenarios
 */
export const clusterFailureScenarios = {
  podCrashLoop: {
    query: 'nginx pod is crashing',
    expectedResponse: /CrashLoopBackOff/,
    weatherState: 'cloudy'
  },
  nodeNotReady: {
    query: 'node is not ready',
    expectedResponse: /NotReady/,
    weatherState: 'stormy'
  },
  deploymentUnavailable: {
    query: 'deployment has no available replicas',
    expectedResponse: /unavailable replicas/,
    weatherState: 'stormy'
  },
  networkTimeout: {
    query: 'service is timing out',
    expectedResponse: /timeout|connectivity/,
    weatherState: 'cloudy'
  },
  storageFull: {
    query: 'persistent volume is full',
    expectedResponse: /storage|disk|mount/,
    weatherState: 'cloudy'
  },
  rbacForbidden: {
    query: 'access denied to resource',
    expectedResponse: /permission|forbidden|rbac/,
    weatherState: 'cloudy'
  }
};

/**
 * Error simulation utilities
 */
export async function simulateNetworkError(page: Page) {
  // Block API calls to simulate network issues
  await page.route('**/api/**', route => route.abort());
}

export async function simulateAuthError(page: Page) {
  await page.route('**/api/credentials/aws', route =>
    route.fulfill({ status: 401, json: { error: 'Invalid credentials' } })
  );
}

export async function simulateClusterUnavailable(page: Page) {
  await page.route('**/api/clusters', route =>
    route.fulfill({ status: 503, json: { error: 'Cluster unreachable' } })
  );
}