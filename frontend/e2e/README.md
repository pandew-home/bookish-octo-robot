# DevOps Chatbot v2.0 - Playwright E2E Testing Plan

## Overview

This document outlines the comprehensive end-to-end testing strategy for the DevOps Chatbot v2.0 application using Playwright. The testing suite covers authentication, cluster management, real-time health monitoring, troubleshooting chat, and comprehensive error scenarios.

## Architecture Under Test

The DevOps Chatbot v2.0 consists of:
- **Frontend**: React + TypeScript application with Material-UI
- **Backend**: FastAPI application with K8sGPT integration
- **Infrastructure**: Kubernetes deployment with K8sGPT operator per cluster
- **Authentication**: Kion AWS credentials for multi-cluster access

## Testing Strategy

### Test Categories

1. **Authentication Flow Tests** - Kion credential validation and session management
2. **Cluster Management Tests** - EKS cluster discovery, selection, and switching
3. **Weather Widget Tests** - Real-time cluster health monitoring via K8sGPT
4. **Chat Interface Tests** - Troubleshooting queries with RAG and K8sGPT integration
5. **Error Scenario Tests** - Network failures, authentication issues, cluster unavailability
6. **Cluster Failure Tests** - Pod crashes, node issues, deployment problems

### Test Environment Setup

#### Prerequisites
```bash
# Install dependencies
npm install

# Install Playwright browsers
npx playwright install

# Start the application (requires backend running)
npm start
```

#### Configuration
- **Base URL**: `http://localhost:3000` (configurable via `BASE_URL` env var)
- **Backend Mocking**: Extensive use of Playwright's `page.route()` for API mocking
- **Test Data**: Realistic mock data for clusters, K8sGPT results, and chat responses

## Test Structure

### Page Objects (`page-objects.ts`)
Reusable page object classes for consistent element interaction:
- `LoginPage` - Authentication form interactions
- `ClusterPage` - Cluster discovery and selection
- `MainAppPage` - Main application interface
- `ChatInterface` - Chat functionality
- `WeatherWidget` - Health monitoring display
- `ResultsPanel` - K8sGPT findings display
- `CredentialBadge` - Session status management

### Test Utilities (`test-utils.ts`)
Shared utilities and mock data:
- Mock AWS credentials and cluster data
- Weather states (sunny, cloudy, stormy)
- Chat responses with citations and K8sGPT findings
- Error simulation helpers
- Common test scenarios

### Test Files

#### `auth.spec.ts` - Authentication Tests
- Login form validation and submission
- Credential format validation
- Session management and expiration
- Error handling for invalid credentials

#### `cluster.spec.ts` - Cluster Management Tests
- Cluster discovery from AWS credentials
- Cluster selection and bearer token generation
- Multi-cluster support and switching
- Error handling for unreachable clusters

#### `weather.spec.ts` - Health Monitoring Tests
- Weather state calculation (sunny/cloudy/stormy)
- K8sGPT result integration
- Real-time polling (60-second intervals)
- Tool health status display
- Issue clicking and chat pre-filling

#### `chat.spec.ts` - Chat Interface Tests
- Message sending and response display
- Citation and K8sGPT finding integration
- Safety notice display for destructive actions
- Conversation history management
- Rate limiting and error handling

#### `error-scenarios.spec.ts` - Error and Failure Tests
- Network connectivity failures
- Authentication expiration scenarios
- Cluster unavailability and RBAC issues
- K8sGPT operator problems
- Resource exhaustion and rate limiting
- Data corruption handling

## Key Test Scenarios

### Authentication Flow
```typescript
// Complete authentication journey
test('complete auth flow', async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login(mockCredentials);
  await loginPage.waitForLoginSuccess();
  // Verify main app loads
});
```

### Cluster Health Monitoring
```typescript
// Weather widget with different health states
test('stormy weather display', async ({ page }) => {
  // Setup authenticated session
  const weatherWidget = new WeatherWidget(page);
  await page.route('**/api/weather', mockStormyWeather);

  const state = await weatherWidget.getWeatherState();
  expect(state).toBe('stormy');

  const issues = await weatherWidget.getTopIssues();
  expect(issues).toContain('NotReady');
});
```

### Troubleshooting Chat
```typescript
// Pod crash loop troubleshooting
test('pod crash troubleshooting', async ({ page }) => {
  const chatInterface = new ChatInterface(page);
  await chatInterface.sendMessage('nginx pod is crashing');

  const response = await chatInterface.getLastAssistantMessage();
  expect(response).toMatch(/CrashLoopBackOff/);

  const hasFindings = await chatInterface.hasK8sGPTFindings();
  expect(hasFindings).toBe(true);
});
```

### Error Scenarios
```typescript
// Network failure during chat
test('network failure handling', async ({ page }) => {
  simulateNetworkError(page);
  await chatInterface.sendMessage('test query');

  await expect(page.locator('[data-testid="connection-error"]')).toBeVisible();
});
```

## Cluster Failure Test Cases

### Pod Issues
- **CrashLoopBackOff**: Container startup failures
- **ImagePullBackOff**: Image registry issues
- **Pending**: Resource constraints or scheduling issues
- **OOMKilled**: Memory exhaustion
- **Evicted**: Node pressure or resource quotas

### Deployment Issues
- **Unavailable Replicas**: Failed rollout or resource issues
- **ProgressDeadlineExceeded**: Stuck deployments
- **FailedCreate**: RBAC or resource creation failures

### Node Health Issues
- **NotReady**: Kubelet or network issues
- **DiskPressure**: Storage capacity issues
- **MemoryPressure**: Memory exhaustion
- **PIDPressure**: Process limits exceeded
- **NetworkUnavailable**: CNI plugin failures

### Networking Issues
- **Service Timeouts**: Load balancer or DNS issues
- **Connection Refused**: Service endpoint problems
- **502/503/504 Errors**: Ingress or backend issues

### Storage Issues
- **PVC Pending**: Storage class or capacity issues
- **Volume Mount Failures**: Permission or path issues
- **Disk Full**: Storage exhaustion scenarios

### Security/RBAC Issues
- **Access Denied**: Insufficient permissions
- **Forbidden Resources**: RBAC policy violations
- **Certificate Issues**: TLS/SSL validation failures

## Mock Data Strategy

### Realistic Test Data
- **Clusters**: Dev, staging, prod environments with realistic metadata
- **K8sGPT Results**: Actual CRD structures with severity levels and analyzer data
- **Chat Responses**: Structured responses with citations, findings, and safety notices
- **Error Responses**: Proper HTTP status codes and error messages

### Dynamic Mocking
```typescript
// Conditional responses based on test context
await page.route('**/api/chat', async route => {
  const request = route.request();
  const body = request.postDataJSON();

  if (body.query.includes('crash')) {
    await route.fulfill({ status: 200, json: podCrashResponse });
  } else {
    await route.fulfill({ status: 200, json: genericResponse });
  }
});
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm ci
      - run: npx playwright install
      - run: npm run test:e2e
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: playwright-report/
```

### Parallel Execution
```typescript
// playwright.config.ts
export default defineConfig({
  workers: process.env.CI ? 1 : undefined, // Parallel in development
  retries: process.env.CI ? 2 : 0,        // Retry on CI failures
  fullyParallel: true,                    // Run tests in parallel
});
```

## Test Maintenance

### Adding New Test Cases
1. Identify the test category (auth, cluster, weather, chat, error)
2. Add test data to `test-utils.ts` if needed
3. Create or extend page objects for new interactions
4. Write the test following existing patterns
5. Update this README with new scenarios

### Debugging Failed Tests
```bash
# Run specific test with debugging
npx playwright test --debug auth.spec.ts

# Run with UI mode for interactive debugging
npm run test:e2e:ui

# Generate and view HTML report
npx playwright show-report
```

### Updating Mock Data
- Keep mock data synchronized with backend API changes
- Use realistic data that matches production scenarios
- Update test expectations when API contracts change

## Performance Considerations

### Test Execution Time
- **Parallel Execution**: Tests run in parallel for faster execution
- **Smart Waiting**: Use `waitFor` methods instead of fixed timeouts
- **Selective Mocking**: Only mock necessary API calls

### Resource Usage
- **Browser Instances**: Shared browser context where possible
- **Memory Management**: Clean up large response mocks
- **Network Efficiency**: Cache repeated mock responses

## Accessibility Testing

### Keyboard Navigation
```typescript
test('keyboard navigation', async ({ page }) => {
  // Test Tab navigation through form elements
  await page.keyboard.press('Tab');
  await expect(page.locator('[data-testid="access-key-input"]')).toBeFocused();
});
```

### Screen Reader Support
```typescript
test('screen reader support', async ({ page }) => {
  // Verify ARIA labels and roles
  await expect(page.locator('[role="alert"]')).toHaveAttribute('aria-live', 'assertive');
});
```

## Future Enhancements

### Visual Regression Testing
```typescript
// Screenshot comparison for UI changes
test('visual regression', async ({ page }) => {
  await expect(page).toHaveScreenshot('login-page.png');
});
```

### API Contract Testing
- Validate API responses match expected schemas
- Test edge cases and error conditions
- Ensure backward compatibility

### Load Testing Integration
- Simulate multiple concurrent users
- Test application performance under load
- Validate rate limiting behavior

## Conclusion

This comprehensive testing plan ensures the DevOps Chatbot v2.0 provides reliable troubleshooting capabilities across diverse Kubernetes failure scenarios. The Playwright-based E2E tests validate the complete user journey from authentication through complex troubleshooting scenarios, with extensive error handling and realistic cluster failure simulations.