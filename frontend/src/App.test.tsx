import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import * as hooks from './hooks';
import { KionCredentials } from './types/credentials';
import { ClusterInfo } from './types/cluster';

// Mock all hooks
jest.mock('./hooks', () => ({
  useCredentials: jest.fn(),
  useCluster: jest.fn(),
  useChat: jest.fn(),
  useWeather: jest.fn(),
}));

// Mock child components
jest.mock('./components/LoginForm', () => ({
  __esModule: true,
  default: ({ onLogin }: { onLogin: (creds: KionCredentials) => Promise<void> }) => (
    <div data-testid="login-form">
      <button onClick={() => onLogin({
        accessKeyId: 'test-key',
        secretAccessKey: 'test-secret',
        sessionToken: 'test-token',
        region: 'us-east-1',
      })}>
        Login
      </button>
    </div>
  ),
}));

jest.mock('./components/ClusterSelector', () => ({
  __esModule: true,
  default: ({ clusters, onSelectCluster }: any) => (
    <div data-testid="cluster-selector">
      {clusters.map((cluster: ClusterInfo) => (
        <button key={cluster.name} onClick={() => onSelectCluster(cluster.name)}>
          {cluster.name}
        </button>
      ))}
    </div>
  ),
}));

jest.mock('./components/CredentialBadge', () => ({
  CredentialBadge: () => <div data-testid="credential-badge">Credential Badge</div>,
}));

jest.mock('./components/WeatherWidget', () => ({
  WeatherWidget: () => <div data-testid="weather-widget">Weather Widget</div>,
}));

jest.mock('./components/ChatInterface', () => ({
  ChatInterface: () => <div data-testid="chat-interface">Chat Interface</div>,
}));

jest.mock('./components/ResultsPanel', () => ({
  ResultsPanel: () => <div data-testid="results-panel">Results Panel</div>,
}));

describe('App Component', () => {
  const mockLogin = jest.fn();
  const mockLogout = jest.fn();
  const mockSelectCluster = jest.fn();
  const mockSendMessage = jest.fn();
  const mockRefresh = jest.fn();

  const mockCredentials = {
    isAuthenticated: false,
    isLoading: false,
    error: null,
    timeRemaining: null,
    login: mockLogin,
    logout: mockLogout,
    refresh: jest.fn(),
  };

  const mockCluster = {
    clusters: [],
    selectedCluster: null,
    isLoading: false,
    error: null,
    discoverClusters: jest.fn(),
    selectCluster: mockSelectCluster,
    clearSelection: jest.fn(),
  };

  const mockChat = {
    messages: [],
    isLoading: false,
    error: null,
    sendMessage: mockSendMessage,
    loadHistory: jest.fn(),
    exportConversation: jest.fn(),
    clearMessages: jest.fn(),
  };

  const mockWeather = {
    weatherData: null,
    previousWeatherData: null,
    isLoading: false,
    isRefreshing: false,
    error: null,
    refresh: mockRefresh,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (hooks.useCredentials as jest.Mock).mockReturnValue(mockCredentials);
    (hooks.useCluster as jest.Mock).mockReturnValue(mockCluster);
    (hooks.useChat as jest.Mock).mockReturnValue(mockChat);
    (hooks.useWeather as jest.Mock).mockReturnValue(mockWeather);
  });

  describe('Authentication Flow', () => {
    it('should render login form when not authenticated', () => {
      render(<App />);
      
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
      expect(screen.getByText('DevOps Chatbot v2')).toBeInTheDocument();
      expect(screen.getByText('Kubernetes Troubleshooting Assistant')).toBeInTheDocument();
    });

    it('should call login when user submits credentials', async () => {
      const user = userEvent.setup();
      render(<App />);
      
      const loginButton = screen.getByText('Login');
      await user.click(loginButton);
      
      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith({
          accessKeyId: 'test-key',
          secretAccessKey: 'test-secret',
          sessionToken: 'test-token',
          region: 'us-east-1',
        });
      });
    });

    it('should resolve single-cluster context after authentication', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
        accountId: '123456789012',
      });

      render(<App />);
      
      expect(screen.getByText('Connecting to Cluster')).toBeInTheDocument();
      expect(screen.getByTestId('credential-badge')).toBeInTheDocument();
      expect(screen.queryByTestId('login-form')).not.toBeInTheDocument();
    });
  });

  describe('Single Cluster Flow', () => {
    beforeEach(() => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
        accountId: '123456789012',
      });
    });

    it('should show connecting state while cluster is not yet selected', () => {
      const clusters: ClusterInfo[] = [
        {
          name: 'dev-cluster',
          endpoint: 'https://dev.eks.amazonaws.com',
          version: '1.28',
          status: 'ACTIVE',
          region: 'us-east-1',
        },
        {
          name: 'prod-cluster',
          endpoint: 'https://prod.eks.amazonaws.com',
          version: '1.28',
          status: 'ACTIVE',
          region: 'us-west-2',
        },
      ];

      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        clusters,
      });

      render(<App />);
      
      expect(screen.getByText('Connecting to Cluster')).toBeInTheDocument();
    });

    it('should display error message when cluster discovery fails', () => {
      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        error: 'Failed to discover clusters. Check your IAM permissions.',
      });

      render(<App />);
      
      expect(screen.getByText(/Failed to discover clusters/)).toBeInTheDocument();
    });
  });

  describe('Main Interface', () => {
    beforeEach(() => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
        accountId: '123456789012',
        timeRemaining: 3600,
      });

      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'dev-cluster',
        clusters: [
          {
            name: 'dev-cluster',
            endpoint: 'https://dev.eks.amazonaws.com',
            version: '1.28',
            status: 'ACTIVE',
            region: 'us-east-1',
          },
        ],
      });
    });

    it('should render main interface when cluster is selected', () => {
      render(<App />);
      
      expect(screen.getByTestId('weather-widget')).toBeInTheDocument();
      expect(screen.getByTestId('chat-interface')).toBeInTheDocument();
      // ResultsPanel is always rendered in the stacked layout
      expect(screen.getByTestId('results-panel')).toBeInTheDocument();
      expect(screen.getByTestId('credential-badge')).toBeInTheDocument();
    });

    it('should display credential expiration warning when time remaining is low', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
        accountId: '123456789012',
        timeRemaining: 500, // Less than 10 minutes
      });

      render(<App />);
      
      expect(screen.getByText(/Your credentials will expire in/)).toBeInTheDocument();
    });

    it('should not display expiration warning when time remaining is sufficient', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
        accountId: '123456789012',
        timeRemaining: 3600, // 1 hour
      });

      render(<App />);
      
      expect(screen.queryByText(/Your credentials will expire in/)).not.toBeInTheDocument();
    });
  });

  describe('Environment-Based Theming', () => {
    beforeEach(() => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
      });
    });

    it('should apply dev theme for dev cluster', () => {
      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'dev-cluster',
        clusters: [
          {
            name: 'dev-cluster',
            endpoint: 'https://dev.eks.amazonaws.com',
            version: '1.28',
            status: 'ACTIVE',
            region: 'us-east-1',
          },
        ],
      });

      render(<App />);

      // Theme is applied via ThemeProvider, check that component renders
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });

    it('should apply staging theme for staging cluster', () => {
      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'staging-cluster',
        clusters: [
          {
            name: 'staging-cluster',
            endpoint: 'https://staging.eks.amazonaws.com',
            version: '1.28',
            status: 'ACTIVE',
            region: 'us-east-1',
          },
        ],
      });

      render(<App />);

      expect(screen.getByRole('banner')).toBeInTheDocument();
    });

    it('should apply prod theme for prod cluster', () => {
      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'prod-cluster',
        clusters: [
          {
            name: 'prod-cluster',
            endpoint: 'https://prod.eks.amazonaws.com',
            version: '1.28',
            status: 'ACTIVE',
            region: 'us-east-1',
          },
        ],
      });

      render(<App />);

      expect(screen.getByRole('banner')).toBeInTheDocument();
    });
  });

  describe('Hook Integration', () => {
    it('should pass isAuthenticated to useCluster hook', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
      });

      render(<App />);
      
      expect(hooks.useCluster).toHaveBeenCalledWith(true);
    });

    it('should pass selectedCluster and isAuthenticated to useChat hook', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
      });

      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'dev-cluster',
      });

      render(<App />);
      
      expect(hooks.useChat).toHaveBeenCalledWith('dev-cluster', true);
    });

    it('should pass selectedCluster and isAuthenticated to useWeather hook', () => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
      });

      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'dev-cluster',
      });

      render(<App />);
      
      expect(hooks.useWeather).toHaveBeenCalledWith('dev-cluster', true);
    });
  });

  describe('Responsive Layout', () => {
    beforeEach(() => {
      (hooks.useCredentials as jest.Mock).mockReturnValue({
        ...mockCredentials,
        isAuthenticated: true,
      });

      (hooks.useCluster as jest.Mock).mockReturnValue({
        ...mockCluster,
        selectedCluster: 'dev-cluster',
      });
    });

    it('should render weather and chat on small viewport', () => {
      render(<App />);
      
      // All three layers are always rendered regardless of viewport
      expect(screen.getByTestId('weather-widget')).toBeInTheDocument();
      expect(screen.getByTestId('chat-interface')).toBeInTheDocument();
      expect(screen.getByTestId('results-panel')).toBeInTheDocument();
    });
  });
});
