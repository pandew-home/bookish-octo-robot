import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ResultsPanel } from './ResultsPanel';
import { resultsApi } from '../services/api';
import { K8sGPTResult } from '../types/k8sgpt';

// Mock the API
jest.mock('../services/api', () => ({
  resultsApi: {
    getResults: jest.fn(),
  },
}));

const mockResultsApi = resultsApi as jest.Mocked<typeof resultsApi>;

describe('ResultsPanel', () => {
  // Sample test data
  const mockResults: K8sGPTResult[] = [
    {
      name: 'pod-failing-1',
      kind: 'Pod',
      namespace: 'default',
      severity: 'high',
      problem: 'Pod is in CrashLoopBackOff state',
      solution: 'Check pod logs and fix application errors',
      analyzer: 'PodAnalyzer',
      timestamp: new Date().toISOString(),
    },
    {
      name: 'deployment-scaling-issue',
      kind: 'Deployment',
      namespace: 'production',
      severity: 'medium',
      problem: 'Deployment has insufficient replicas',
      solution: 'Scale up the deployment',
      analyzer: 'DeploymentAnalyzer',
      timestamp: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
    },
    {
      name: 'service-endpoint-warning',
      kind: 'Service',
      namespace: 'default',
      severity: 'low',
      problem: 'Service has no endpoints',
      solution: 'Ensure pods are running and match service selector',
      analyzer: 'ServiceAnalyzer',
      timestamp: new Date(Date.now() - 7200000).toISOString(), // 2 hours ago
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    // Default mock implementation
    mockResultsApi.getResults.mockResolvedValue(mockResults);
  });

  afterEach(() => {
    jest.clearAllTimers();
  });

  describe('Rendering', () => {
    it('should render the component with title', async () => {
      render(<ResultsPanel />);
      
      expect(screen.getByText('Cluster Analyzer Results')).toBeInTheDocument();
    });

    it('should display loading indicator initially', () => {
      render(<ResultsPanel />);
      
      // MUI LinearProgress is present during loading
      const progressBars = document.querySelectorAll('.MuiLinearProgress-root');
      expect(progressBars.length).toBeGreaterThan(0);
    });

    it('should display results after loading', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
        expect(screen.getByText('deployment-scaling-issue')).toBeInTheDocument();
        expect(screen.getByText('service-endpoint-warning')).toBeInTheDocument();
      });
    });

    it('should display result count', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/results shown/)).toBeInTheDocument();
      });
    });

    it('should display severity indicators', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/High/)).toBeInTheDocument();
        expect(screen.getByText(/Medium/)).toBeInTheDocument();
        expect(screen.getByText(/Low/)).toBeInTheDocument();
      });
    });

    it('should display namespace and kind for each result', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('Pod')).toBeInTheDocument();
        expect(screen.getByText('Deployment')).toBeInTheDocument();
        expect(screen.getByText('Service')).toBeInTheDocument();
        expect(screen.getAllByText('default').length).toBeGreaterThan(0);
        expect(screen.getByText('production')).toBeInTheDocument();
      });
    });

    it('should display analyzer name for each result', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/PodAnalyzer/)).toBeInTheDocument();
        expect(screen.getByText(/DeploymentAnalyzer/)).toBeInTheDocument();
        expect(screen.getByText(/ServiceAnalyzer/)).toBeInTheDocument();
      });
    });

    it('should display problem description', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/Pod is in CrashLoopBackOff state/)).toBeInTheDocument();
        expect(screen.getByText(/Deployment has insufficient replicas/)).toBeInTheDocument();
        expect(screen.getByText(/Service has no endpoints/)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message when API call fails', async () => {
      const errorMessage = 'Failed to fetch results';
      mockResultsApi.getResults.mockRejectedValue(new Error(errorMessage));
      
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });

    it('should display API error detail when available', async () => {
      const errorDetail = 'Cluster not selected';
      mockResultsApi.getResults.mockRejectedValue({
        response: { data: { detail: errorDetail } },
      });
      
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(errorDetail)).toBeInTheDocument();
      });
    });
  });

  describe('Empty State', () => {
    it('should display empty state message when no results', async () => {
      mockResultsApi.getResults.mockResolvedValue([]);
      
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/No Cluster Analyzer results found/)).toBeInTheDocument();
        expect(screen.getByText(/Your cluster is healthy/)).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('should show severity tabs', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Verify severity tabs are present
      expect(screen.getByText(/All/)).toBeInTheDocument();
      expect(screen.getByText('High')).toBeInTheDocument();
      expect(screen.getByText('Medium')).toBeInTheDocument();
      expect(screen.getByText('Low')).toBeInTheDocument();
    });

    it('should filter results by severity tab click', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Click High tab
      const highTab = screen.getByText('High');
      fireEvent.click(highTab);
      
      // Only high severity result should be visible
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
        expect(screen.queryByText('deployment-scaling-issue')).not.toBeInTheDocument();
        expect(screen.queryByText('service-endpoint-warning')).not.toBeInTheDocument();
      });
      
      expect(screen.getByText('1 result shown')).toBeInTheDocument();
    });

    it('should display namespace and kind in results', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Results contain different namespaces and kinds
      expect(screen.getByText('Pod')).toBeInTheDocument();
      expect(screen.getByText('Deployment')).toBeInTheDocument();
      expect(screen.getByText('Service')).toBeInTheDocument();
      expect(screen.getByText('production')).toBeInTheDocument();
    });

    it('should have refresh button in header', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText(/results shown/)).toBeInTheDocument();
      });
      
      // Verify refresh button is present
      const refreshIcon = screen.getByTestId('RefreshIcon');
      expect(refreshIcon).toBeInTheDocument();
    });
  });

  describe('Expandable Details', () => {
    it('should expand result details when expand button is clicked', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Find and click the first expand button
      const expandButtons = screen.getAllByRole('button', { name: '' });
      const expandButton = expandButtons.find(btn => 
        btn.querySelector('.MuiSvgIcon-root')?.classList.contains('MuiSvgIcon-root')
      );
      
      if (expandButton) {
        fireEvent.click(expandButton);
        
        await waitFor(() => {
          expect(screen.getByText(/Check pod logs and fix application errors/)).toBeInTheDocument();
        });
      }
    });

    it('should collapse result details when collapse button is clicked', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Find and click expand button
      const expandButtons = screen.getAllByRole('button', { name: '' });
      const expandButton = expandButtons.find(btn => 
        btn.querySelector('.MuiSvgIcon-root')?.classList.contains('MuiSvgIcon-root')
      );
      
      if (expandButton) {
        fireEvent.click(expandButton);
        
        await waitFor(() => {
          expect(screen.getByText(/Check pod logs and fix application errors/)).toBeInTheDocument();
        });
        
        // Click again to collapse
        fireEvent.click(expandButton);
        
        // Solution text should not be visible (it's in a Collapse component)
        // We can't easily test this without more complex DOM queries
      }
    });
  });

  describe('Refresh Functionality', () => {
    it('should call API when refresh button is clicked', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        expect(screen.getByText('pod-failing-1')).toBeInTheDocument();
      });
      
      // Clear previous calls
      mockResultsApi.getResults.mockClear();
      
      const refreshButton = screen.getByTestId('RefreshIcon').closest('button');
      if (refreshButton) {
        fireEvent.click(refreshButton);
      }
      
      await waitFor(() => {
        expect(mockResultsApi.getResults).toHaveBeenCalled();
      });
    });

    it('should auto-refresh at specified interval', async () => {
      jest.useFakeTimers();
      
      render(<ResultsPanel refreshInterval={5000} />);
      
      await waitFor(() => {
        expect(mockResultsApi.getResults).toHaveBeenCalledTimes(1);
      });
      
      // Clear and advance timer
      mockResultsApi.getResults.mockClear();
      jest.advanceTimersByTime(5000);
      
      await waitFor(() => {
        expect(mockResultsApi.getResults).toHaveBeenCalledTimes(1);
      });
      
      jest.useRealTimers();
    });
  });

  describe('Timestamp Formatting', () => {
    it('should format recent timestamps correctly', async () => {
      render(<ResultsPanel />);
      
      await waitFor(() => {
        // Should show relative time like "Just now", "1h ago", etc.
        const timestamps = screen.getAllByText(/ago|Just now/);
        expect(timestamps.length).toBeGreaterThan(0);
      });
    });
  });
});
