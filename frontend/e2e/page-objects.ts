import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for DevOps Chatbot application
 */

export class LoginPage {
  readonly page: Page;
  readonly accessKeyInput: Locator;
  readonly secretKeyInput: Locator;
  readonly sessionTokenInput: Locator;
  readonly regionSelect: Locator;
  readonly loginButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.accessKeyInput = page.locator('[data-testid="access-key-input"]');
    this.secretKeyInput = page.locator('[data-testid="secret-key-input"]');
    this.sessionTokenInput = page.locator('[data-testid="session-token-input"]');
    this.regionSelect = page.locator('[data-testid="region-select"]');
    this.loginButton = page.locator('[data-testid="login-button"]');
    this.errorMessage = page.locator('[data-testid="error-message"]');
  }

  async goto() {
    await this.page.goto('/');
  }

  async login(credentials: { accessKeyId: string; secretAccessKey: string; sessionToken: string; region: string }) {
    await this.accessKeyInput.fill(credentials.accessKeyId);
    await this.secretKeyInput.fill(credentials.secretAccessKey);
    await this.sessionTokenInput.fill(credentials.sessionToken);
    await this.regionSelect.selectOption(credentials.region);
    await this.loginButton.click();
  }

  async waitForLoginSuccess() {
    await this.page.waitForURL('**/clusters');
  }
}

export class ClusterPage {
  readonly page: Page;
  readonly clusterSelector: Locator;
  readonly selectButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly clusters: Locator;

  constructor(page: Page) {
    this.page = page;
    this.clusterSelector = page.locator('[data-testid="cluster-selector"]');
    this.selectButton = page.locator('[data-testid="select-cluster-button"]');
    this.loadingSpinner = page.locator('[data-testid="loading-spinner"]');
    this.errorMessage = page.locator('[data-testid="error-message"]');
    this.clusters = page.locator('[data-testid="cluster-item"]');
  }

  async selectCluster(clusterName: string) {
    await this.clusterSelector.selectOption(clusterName);
    await this.selectButton.click();
  }

  async waitForMainApp() {
    await this.page.waitForSelector('[data-testid="weather-widget"]');
  }

  async getClusterCount() {
    return await this.clusters.count();
  }

  async getClusterNames() {
    return await this.clusters.allTextContents();
  }
}

export class MainAppPage {
  readonly page: Page;
  readonly appBar: Locator;
  readonly weatherWidget: Locator;
  readonly chatInterface: Locator;
  readonly resultsPanel: Locator;
  readonly credentialBadge: Locator;
  readonly clusterSelector: Locator;

  constructor(page: Page) {
    this.page = page;
    this.appBar = page.locator('[data-testid="app-bar"]');
    this.weatherWidget = page.locator('[data-testid="weather-widget"]');
    this.chatInterface = page.locator('[data-testid="chat-interface"]');
    this.resultsPanel = page.locator('[data-testid="results-panel"]');
    this.credentialBadge = page.locator('[data-testid="credential-badge"]');
    this.clusterSelector = page.locator('[data-testid="cluster-selector"]');
  }

  async waitForLoad() {
    await this.weatherWidget.waitFor();
    await this.chatInterface.waitFor();
  }

  async getWeatherState() {
    return await this.weatherWidget.getAttribute('data-weather-state');
  }

  async getClusterHealthIssues() {
    return await this.weatherWidget.locator('[data-testid="health-issue"]').allTextContents();
  }

  async switchCluster(clusterName: string) {
    await this.clusterSelector.selectOption(clusterName);
    await this.page.waitForLoadState('networkidle');
  }
}

export class ChatInterface {
  readonly page: Page;
  readonly input: Locator;
  readonly sendButton: Locator;
  readonly messages: Locator;
  readonly userMessages: Locator;
  readonly assistantMessages: Locator;
  readonly citations: Locator;
  readonly k8sgptFindings: Locator;
  readonly safetyNotices: Locator;

  constructor(page: Page) {
    this.page = page;
    this.input = page.locator('[data-testid="chat-input"]');
    this.sendButton = page.locator('[data-testid="send-button"]');
    this.messages = page.locator('[data-testid="chat-message"]');
    this.userMessages = page.locator('[data-testid="user-message"]');
    this.assistantMessages = page.locator('[data-testid="assistant-message"]');
    this.citations = page.locator('[data-testid="citation"]');
    this.k8sgptFindings = page.locator('[data-testid="k8sgpt-finding"]');
    this.safetyNotices = page.locator('[data-testid="safety-notice"]');
  }

  async sendMessage(message: string) {
    await this.input.fill(message);
    await this.sendButton.click();
    await this.page.waitForSelector('[data-testid="assistant-message"]');
  }

  async getLastAssistantMessage() {
    const messages = await this.assistantMessages.allTextContents();
    return messages[messages.length - 1];
  }

  async getMessageCount() {
    return await this.messages.count();
  }

  async hasCitations() {
    return await this.citations.count() > 0;
  }

  async hasK8sGPTFindings() {
    return await this.k8sgptFindings.count() > 0;
  }

  async hasSafetyNotice() {
    return await this.safetyNotices.count() > 0;
  }
}

export class WeatherWidget {
  readonly page: Page;
  readonly widget: Locator;
  readonly stateIcon: Locator;
  readonly clusterName: Locator;
  readonly issueCount: Locator;
  readonly topIssues: Locator;
  readonly toolsStatus: Locator;

  constructor(page: Page) {
    this.page = page;
    this.widget = page.locator('[data-testid="weather-widget"]');
    this.stateIcon = page.locator('[data-testid="weather-state-icon"]');
    this.clusterName = page.locator('[data-testid="cluster-name"]');
    this.issueCount = page.locator('[data-testid="issue-count"]');
    this.topIssues = page.locator('[data-testid="top-issue"]');
    this.toolsStatus = page.locator('[data-testid="tool-status"]');
  }

  async getWeatherState() {
    return await this.widget.getAttribute('data-weather-state');
  }

  async getClusterName() {
    return await this.clusterName.textContent();
  }

  async getIssueCount() {
    const text = await this.issueCount.textContent();
    return parseInt(text || '0');
  }

  async getTopIssues() {
    return await this.topIssues.allTextContents();
  }

  async getToolsStatus() {
    const tools = await this.toolsStatus.all();
    const status: Record<string, string> = {};

    for (const tool of tools) {
      const name = await tool.getAttribute('data-tool-name');
      const state = await tool.getAttribute('data-tool-status');
      if (name && state) {
        status[name] = state;
      }
    }

    return status;
  }

  async clickOnIssue(index: number = 0) {
    const issues = this.topIssues.nth(index);
    await issues.click();
  }
}

export class ResultsPanel {
  readonly page: Page;
  readonly panel: Locator;
  readonly k8sgptResults: Locator;
  readonly filters: Locator;
  readonly resultDetails: Locator;

  constructor(page: Page) {
    this.page = page;
    this.panel = page.locator('[data-testid="results-panel"]');
    this.k8sgptResults = page.locator('[data-testid="k8sgpt-result"]');
    this.filters = page.locator('[data-testid="result-filter"]');
    this.resultDetails = page.locator('[data-testid="result-details"]');
  }

  async getResultCount() {
    return await this.k8sgptResults.count();
  }

  async getResultsBySeverity(severity: string) {
    return await this.k8sgptResults.filter({ hasText: severity }).allTextContents();
  }

  async filterByNamespace(namespace: string) {
    await this.filters.selectOption(namespace);
  }

  async expandResult(index: number = 0) {
    await this.k8sgptResults.nth(index).click();
    await this.resultDetails.waitFor();
  }

  async getResultDetails() {
    return await this.resultDetails.textContent();
  }
}

export class CredentialBadge {
  readonly page: Page;
  readonly badge: Locator;
  readonly timeRemaining: Locator;
  readonly logoutButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.badge = page.locator('[data-testid="credential-badge"]');
    this.timeRemaining = page.locator('[data-testid="time-remaining"]');
    this.logoutButton = page.locator('[data-testid="logout-button"]');
  }

  async getTimeRemaining() {
    const text = await this.timeRemaining.textContent();
    return text;
  }

  async isExpiringSoon() {
    return await this.badge.getAttribute('data-expiring-soon') === 'true';
  }

  async logout() {
    await this.logoutButton.click();
  }
}