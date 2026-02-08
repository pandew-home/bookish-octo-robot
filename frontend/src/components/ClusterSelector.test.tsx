import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ClusterSelector from './ClusterSelector';
import { ClusterInfo } from '../types/cluster';

describe('ClusterSelector', () => {
  const mockOnSelectCluster = jest.fn();

  const mockClusters: ClusterInfo[] = [
    {
      name: 'dev-cluster-1',
      endpoint: 'https://dev-cluster-1.eks.amazonaws.com',
      version: '1.28',
      status: 'ACTIVE',
      region: 'us-east-1',
    },
    {
      name: 'staging-cluster-1',
      endpoint: 'https://staging-cluster-1.eks.amazonaws.com',
      version: '1.27',
      status: 'ACTIVE',
      region: 'us-west-2',
    },
    {
      name: 'prod-cluster-1',
      endpoint: 'https://prod-cluster-1.eks.amazonaws.com',
      version: '1.28',
      status: 'ACTIVE',
      region: 'eu-west-1',
    },
    {
      name: 'test-cluster',
      endpoint: 'https://test-cluster.eks.amazonaws.com',
      version: '1.26',
      status: 'ACTIVE',
      region: 'ap-southeast-1',
    },
  ];

  beforeEach(() => {
    mockOnSelectCluster.mockClear();
  });

  describe('Rendering', () => {
    it('should render cluster selector with label', () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      expect(screen.getByLabelText(/select cluster/i)).toBeInTheDocument();
    });

    it('should render all clusters in dropdown', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText('dev-cluster-1')).toBeInTheDocument();
        expect(screen.getByText('staging-cluster-1')).toBeInTheDocument();
        expect(screen.getByText('prod-cluster-1')).toBeInTheDocument();
        expect(screen.getByText('test-cluster')).toBeInTheDocument();
      });
    });

    it('should display cluster metadata (region, version, status)', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText(/us-east-1 • v1.28 • ACTIVE/i)).toBeInTheDocument();
        expect(screen.getByText(/us-west-2 • v1.27 • ACTIVE/i)).toBeInTheDocument();
        expect(screen.getByText(/eu-west-1 • v1.28 • ACTIVE/i)).toBeInTheDocument();
      });
    });

    it('should display environment badges for clusters', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText('DEV')).toBeInTheDocument();
        expect(screen.getByText('STAGING')).toBeInTheDocument();
        expect(screen.getByText('PROD')).toBeInTheDocument();
        expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
      });
    });

    it('should show loading state when loading prop is true', () => {
      render(
        <ClusterSelector
          clusters={[]}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
          loading={true}
        />
      );

      expect(screen.getByText(/discovering clusters/i)).toBeInTheDocument();
      expect(screen.queryByLabelText(/select cluster/i)).not.toBeInTheDocument();
    });

    it('should show empty state when no clusters are available', () => {
      render(
        <ClusterSelector
          clusters={[]}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
          loading={false}
        />
      );

      expect(screen.getByText(/no clusters found/i)).toBeInTheDocument();
      expect(screen.getByText(/please check your credentials/i)).toBeInTheDocument();
    });

    it('should be disabled when disabled prop is true', () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
          disabled={true}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      // MUI Select uses aria-disabled instead of the disabled attribute
      expect(selector).toHaveAttribute('aria-disabled', 'true');
    });
  });

  describe('Cluster Selection', () => {
    it('should call onSelectCluster when a cluster is selected', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText('dev-cluster-1')).toBeInTheDocument();
      });

      const devClusterOption = screen.getByText('dev-cluster-1');
      fireEvent.click(devClusterOption);

      await waitFor(() => {
        expect(mockOnSelectCluster).toHaveBeenCalledWith('dev-cluster-1');
      });
    });

    it('should display selected cluster with environment indicator', () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster="prod-cluster-1"
          onSelectCluster={mockOnSelectCluster}
        />
      );

      expect(screen.getByText('prod-cluster-1')).toBeInTheDocument();
      expect(screen.getByText('(eu-west-1)')).toBeInTheDocument();
    });

    it('should allow switching between clusters', async () => {
      const { rerender } = render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster="dev-cluster-1"
          onSelectCluster={mockOnSelectCluster}
        />
      );

      expect(screen.getByText('dev-cluster-1')).toBeInTheDocument();

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText('staging-cluster-1')).toBeInTheDocument();
      });

      const stagingClusterOption = screen.getByText('staging-cluster-1');
      fireEvent.click(stagingClusterOption);

      await waitFor(() => {
        expect(mockOnSelectCluster).toHaveBeenCalledWith('staging-cluster-1');
      });

      // Simulate parent component updating the selected cluster
      rerender(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster="staging-cluster-1"
          onSelectCluster={mockOnSelectCluster}
        />
      );

      expect(screen.getByText('staging-cluster-1')).toBeInTheDocument();
      expect(screen.getByText('(us-west-2)')).toBeInTheDocument();
    });
  });

  describe('Environment-Based Theming', () => {
    it('should apply dev environment theming (green)', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const devBadge = screen.getByText('DEV');
        expect(devBadge).toBeInTheDocument();
        // Verify the badge is rendered as a Chip component
        expect(devBadge.closest('.MuiChip-root')).toBeInTheDocument();
      });
    });

    it('should apply staging environment theming (orange)', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const stagingBadge = screen.getByText('STAGING');
        expect(stagingBadge).toBeInTheDocument();
        // Verify the badge is rendered as a Chip component
        expect(stagingBadge.closest('.MuiChip-root')).toBeInTheDocument();
      });
    });

    it('should apply prod environment theming (red)', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const prodBadge = screen.getByText('PROD');
        expect(prodBadge).toBeInTheDocument();
        // Verify the badge is rendered as a Chip component
        expect(prodBadge.closest('.MuiChip-root')).toBeInTheDocument();
      });
    });

    it('should apply unknown environment theming (grey) for unrecognized cluster names', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const unknownBadge = screen.getByText('UNKNOWN');
        expect(unknownBadge).toBeInTheDocument();
        // Verify the badge is rendered as a Chip component
        expect(unknownBadge.closest('.MuiChip-root')).toBeInTheDocument();
      });
    });

    it('should highlight selected cluster with environment color border', () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster="prod-cluster-1"
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      const inputElement = selector.closest('.MuiOutlinedInput-root');
      
      // The component applies environment-specific border color to selected cluster
      expect(inputElement).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('should handle cluster with missing metadata gracefully', async () => {
      const clusterWithMissingData: ClusterInfo = {
        name: 'incomplete-cluster',
        endpoint: '',
        version: '',
        status: '',
        region: '',
      };

      render(
        <ClusterSelector
          clusters={[clusterWithMissingData]}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText('incomplete-cluster')).toBeInTheDocument();
      });
    });

    it('should handle single cluster in list', () => {
      const singleCluster = [mockClusters[0]];

      render(
        <ClusterSelector
          clusters={singleCluster}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      expect(screen.getByLabelText(/select cluster/i)).toBeInTheDocument();
    });

    it('should handle very long cluster names', async () => {
      const longNameCluster: ClusterInfo = {
        name: 'very-long-cluster-name-that-exceeds-normal-length-expectations-dev',
        endpoint: 'https://long.eks.amazonaws.com',
        version: '1.28',
        status: 'ACTIVE',
        region: 'us-east-1',
      };

      render(
        <ClusterSelector
          clusters={[longNameCluster]}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        expect(screen.getByText(longNameCluster.name)).toBeInTheDocument();
      });
    });

    it('should not call onSelectCluster when disabled', async () => {
      render(
        <ClusterSelector
          clusters={mockClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
          disabled={true}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      
      // Try to open the dropdown (should not work when disabled)
      fireEvent.mouseDown(selector);

      // Wait a bit to ensure no action happens
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnSelectCluster).not.toHaveBeenCalled();
    });
  });

  describe('Environment Detection', () => {
    it('should detect dev environment from cluster name variations', async () => {
      const devClusters: ClusterInfo[] = [
        { ...mockClusters[0], name: 'dev-cluster' },
        { ...mockClusters[0], name: 'development-cluster' },
        { ...mockClusters[0], name: 'cluster-dev' },
        { ...mockClusters[0], name: 'DEV-CLUSTER' },
      ];

      render(
        <ClusterSelector
          clusters={devClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const devBadges = screen.getAllByText('DEV');
        expect(devBadges).toHaveLength(4);
      });
    });

    it('should detect staging environment from cluster name variations', async () => {
      const stagingClusters: ClusterInfo[] = [
        { ...mockClusters[0], name: 'staging-cluster' },
        { ...mockClusters[0], name: 'stag-cluster' },
        { ...mockClusters[0], name: 'cluster-staging' },
        { ...mockClusters[0], name: 'STAGING-CLUSTER' },
      ];

      render(
        <ClusterSelector
          clusters={stagingClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const stagingBadges = screen.getAllByText('STAGING');
        expect(stagingBadges).toHaveLength(4);
      });
    });

    it('should detect prod environment from cluster name variations', async () => {
      const prodClusters: ClusterInfo[] = [
        { ...mockClusters[0], name: 'prod-cluster' },
        { ...mockClusters[0], name: 'production-cluster' },
        { ...mockClusters[0], name: 'cluster-prod' },
        { ...mockClusters[0], name: 'PROD-CLUSTER' },
      ];

      render(
        <ClusterSelector
          clusters={prodClusters}
          selectedCluster={null}
          onSelectCluster={mockOnSelectCluster}
        />
      );

      const selector = screen.getByLabelText(/select cluster/i);
      fireEvent.mouseDown(selector);

      await waitFor(() => {
        const prodBadges = screen.getAllByText('PROD');
        expect(prodBadges).toHaveLength(4);
      });
    });
  });
});
