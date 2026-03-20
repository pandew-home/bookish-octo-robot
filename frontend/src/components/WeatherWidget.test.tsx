import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { WeatherWidget } from './WeatherWidget';

// Mock fetch
global.fetch = jest.fn();

const mockWeatherData = {
  state: 'sunny',
  cluster_name: 'test-cluster',
  cluster_version: '1.28',
  k8sgpt_result_count: 0,
  top_issues: [],
  cluster_tools: [
    {
      name: 'k8sgpt',
      version: '0.3.0',
      category: 'diagnostics',
      deployment_age_days: 5,
      status: 'healthy',
    },
  ],
  timestamp: new Date().toISOString(),
};

describe('WeatherWidget', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockWeatherData,
    });
  });

  afterEach(() => {
    jest.clearAllTimers();
  });

  it('should show loading state initially', () => {
    render(<WeatherWidget />);
    expect(screen.getByText('Loading cluster health...')).toBeInTheDocument();
  });

  it('should display weather data after loading', async () => {
    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    expect(screen.getByText('Sunny')).toBeInTheDocument();
    expect(screen.getByText(/0 K8sGPT results/)).toBeInTheDocument();
  });

  it('should display weather icon for sunny state', async () => {
    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('☀️')).toBeInTheDocument();
    });
  });

  it('should display top issues when present', async () => {
    const dataWithIssues = {
      ...mockWeatherData,
      state: 'cloudy',
      k8sgpt_result_count: 3,
      top_issues: [
        {
          name: 'failing-pod',
          kind: 'Pod',
          namespace: 'default',
          severity: 'high',
          problem: 'Pod is in CrashLoopBackOff',
          solution: 'Check pod logs',
        },
      ],
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => dataWithIssues,
    });

    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('Pod/failing-pod')).toBeInTheDocument();
    });

    expect(screen.getByText('Pod is in CrashLoopBackOff')).toBeInTheDocument();
  });

  it('should show error state when fetch fails', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Should show some error message
    await waitFor(() => {
      expect(screen.getByText(/Network error|Failed to fetch/i)).toBeInTheDocument();
    });
  });

  it('should open details dialog when View Details is clicked', async () => {
    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    const viewDetailsButton = screen.getByText('View Details');
    fireEvent.click(viewDetailsButton);

    await waitFor(() => {
      expect(screen.getByText('Cluster Health Details')).toBeInTheDocument();
    });
  });

  it('should call onAskAboutIssue when quick action is clicked', async () => {
    const mockOnAskAboutIssue = jest.fn();
    
    const dataWithIssues = {
      ...mockWeatherData,
      state: 'cloudy',
      k8sgpt_result_count: 1,
      top_issues: [
        {
          name: 'failing-pod',
          kind: 'Pod',
          namespace: 'default',
          severity: 'high',
          problem: 'Pod is in CrashLoopBackOff',
        },
      ],
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => dataWithIssues,
    });

    render(<WeatherWidget onAskAboutIssue={mockOnAskAboutIssue} />);

    await waitFor(() => {
      expect(screen.getByText('Pod/failing-pod')).toBeInTheDocument();
    });

    const askButton = screen.getByText('Ask About This');
    fireEvent.click(askButton);

    expect(mockOnAskAboutIssue).toHaveBeenCalledWith(
      expect.stringContaining('Pod/failing-pod')
    );
  });

  it('should display cluster tools in details dialog', async () => {
    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    const viewDetailsButton = screen.getByText('View Details');
    fireEvent.click(viewDetailsButton);

    await waitFor(() => {
      expect(screen.getByText('Cluster Health Details')).toBeInTheDocument();
    });

    // Expand cluster tools section
    const toolsButton = screen.getByText(/CLUSTER TOOLS & VERSIONS/);
    fireEvent.click(toolsButton);

    await waitFor(() => {
      expect(screen.getByText('k8sgpt')).toBeInTheDocument();
    });

    expect(screen.getByText('0.3.0')).toBeInTheDocument();
  });

  it('should preserve previous data during refresh', async () => {
    const { rerender } = render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    // Mock a failed refresh
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

    // Trigger a re-render (simulating polling)
    rerender(<WeatherWidget />);

    // Should still show previous data
    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });
  });

  it('should format timestamp correctly', async () => {
    const now = new Date();
    const dataWithRecentTimestamp = {
      ...mockWeatherData,
      timestamp: new Date(now.getTime() - 5 * 60 * 1000).toISOString(), // 5 minutes ago
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => dataWithRecentTimestamp,
    });

    render(<WeatherWidget />);

    await waitFor(() => {
      expect(screen.getByText(/5m ago/)).toBeInTheDocument();
    });
  });
});
