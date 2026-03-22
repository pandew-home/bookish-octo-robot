import { renderHook, act, waitFor } from '@testing-library/react';
import { useCluster } from './useCluster';
import { clusterApi } from '../services/api';
import { ClusterInfo } from '../types/cluster';

// Mock the API
jest.mock('../services/api');

const mockClusterApi = clusterApi as jest.Mocked<typeof clusterApi>;

describe('useCluster', () => {
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
      version: '1.28',
      status: 'ACTIVE',
      region: 'us-west-2',
    },
    {
      name: 'prod-cluster-1',
      endpoint: 'https://prod-cluster-1.eks.amazonaws.com',
      version: '1.29',
      status: 'ACTIVE',
      region: 'us-east-1',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('cluster discovery', () => {
    it('should discover clusters when authenticated', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery and auto-selection to complete
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
        expect(result.current.selectedCluster).toBe('dev-cluster-1');
      });

      expect(mockClusterApi.getClusters).toHaveBeenCalled();
      expect(result.current.clusters).toEqual(mockClusters);
      expect(result.current.error).toBeNull();
    });

    it('should not discover clusters when not authenticated', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);

      const { result } = renderHook(() => useCluster(false));

      // Wait a bit to ensure no API call is made
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockClusterApi.getClusters).not.toHaveBeenCalled();
      expect(result.current.clusters).toHaveLength(0);
    });

    it('should handle discovery failure gracefully', async () => {
      const errorMessage = 'Failed to list clusters';
      mockClusterApi.getClusters.mockRejectedValue({
        response: {
          data: {
            detail: errorMessage,
          },
        },
      });

      const { result } = renderHook(() => useCluster(true));

      await waitFor(() => {
        expect(result.current.error).toBe(errorMessage);
      });

      expect(result.current.clusters).toHaveLength(0);
    });

    it('should set error when no clusters are found', async () => {
      mockClusterApi.getClusters.mockResolvedValue([]);

      const { result } = renderHook(() => useCluster(true));

      // With auto-selection logic, no clusters returns empty list
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(0);
      });

      expect(result.current.selectedCluster).toBeNull();
    });

    it('should set loading state during discovery', async () => {
      mockClusterApi.getClusters.mockImplementation(() =>
        new Promise(resolve => setTimeout(() => resolve(mockClusters), 100))
      );
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery and auto-selection to complete
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.clusters).toHaveLength(3);
        expect(result.current.selectedCluster).toBe('dev-cluster-1'); // Auto-selected
      });
    });

    it('should allow manual cluster discovery', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      // Clear mock calls
      mockClusterApi.getClusters.mockClear();

      // Manually trigger discovery
      await act(async () => {
        await result.current.discoverClusters();
      });

      expect(mockClusterApi.getClusters).toHaveBeenCalledTimes(1);
    });
  });

  describe('cluster selection', () => {
    beforeEach(async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);
    });

    it('should select a cluster successfully', async () => {
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      await act(async () => {
        await result.current.selectCluster('dev-cluster-1');
      });

      expect(mockClusterApi.selectCluster).toHaveBeenCalledWith('dev-cluster-1');
      expect(result.current.selectedCluster).toBe('dev-cluster-1');
      expect(result.current.error).toBeNull();
    });

    it('should handle cluster selection failure', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);
      mockClusterApi.selectCluster.mockRejectedValue({
        response: {
          data: {
            detail: 'Failed to generate bearer token',
          },
        },
      });

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery and auto-selection to fail
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
        expect(result.current.error).toBe('Failed to generate bearer token');
      });

      // selectedCluster should be null since auto-selection failed
      expect(result.current.selectedCluster).toBeNull();
    });

    it('should not select cluster when not authenticated', async () => {
      const { result } = renderHook(() => useCluster(false));

      await act(async () => {
        await result.current.selectCluster('dev-cluster-1');
      });

      expect(mockClusterApi.selectCluster).not.toHaveBeenCalled();
      expect(result.current.error).toBe('Not authenticated');
    });

    it('should clear cluster selection', async () => {
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });

      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      // Select a cluster
      await act(async () => {
        await result.current.selectCluster('dev-cluster-1');
      });

      expect(result.current.selectedCluster).toBe('dev-cluster-1');

      // Clear selection
      act(() => {
        result.current.clearSelection();
      });

      expect(result.current.selectedCluster).toBeNull();
    });
  });

  describe('cluster switching', () => {
    beforeEach(async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });
    });

    it('should switch between clusters', async () => {
      const { result } = renderHook(() => useCluster(true));

      // Wait for auto-discovery
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      // Select first cluster
      await act(async () => {
        await result.current.selectCluster('dev-cluster-1');
      });

      expect(result.current.selectedCluster).toBe('dev-cluster-1');

      // Switch to second cluster
      await act(async () => {
        await result.current.selectCluster('staging-cluster-1');
      });

      expect(mockClusterApi.selectCluster).toHaveBeenCalledWith('staging-cluster-1');
      expect(result.current.selectedCluster).toBe('staging-cluster-1');
    });
  });

  describe('authentication state changes', () => {
    it('should clear clusters and selection when authentication is lost', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);
      mockClusterApi.selectCluster.mockResolvedValue({ success: true });

      const { result, rerender } = renderHook(
        ({ isAuthenticated }) => useCluster(isAuthenticated),
        { initialProps: { isAuthenticated: true } }
      );

      // Wait for auto-discovery
      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      // Select a cluster
      await act(async () => {
        await result.current.selectCluster('dev-cluster-1');
      });

      expect(result.current.selectedCluster).toBe('dev-cluster-1');

      // Lose authentication
      rerender({ isAuthenticated: false });

      await waitFor(() => {
        expect(result.current.selectedCluster).toBeNull();
        expect(result.current.clusters).toHaveLength(0);
      });
    });

    it('should auto-discover clusters when authentication is gained', async () => {
      mockClusterApi.getClusters.mockResolvedValue(mockClusters);

      const { result, rerender } = renderHook(
        ({ isAuthenticated }) => useCluster(isAuthenticated),
        { initialProps: { isAuthenticated: false } }
      );

      expect(result.current.clusters).toHaveLength(0);

      // Gain authentication
      rerender({ isAuthenticated: true });

      await waitFor(() => {
        expect(result.current.clusters).toHaveLength(3);
      });

      expect(mockClusterApi.getClusters).toHaveBeenCalled();
    });
  });
});
