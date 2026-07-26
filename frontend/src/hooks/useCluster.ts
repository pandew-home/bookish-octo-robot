import { useState, useCallback, useEffect } from 'react';
import { ClusterInfo } from '../types/cluster';
import { clusterApi } from '../services/api';
import { formatApiError, toApiError } from '../utils/apiError';

export interface UseClusterState {
  clusters: ClusterInfo[];
  selectedCluster: string | null;
  isLoading: boolean;
  error: string | null;
  discoverClusters: () => Promise<void>;
  selectCluster: (clusterName: string) => Promise<void>;
  clearSelection: () => void;
}

export const useCluster = (isAuthenticated: boolean): UseClusterState => {
  const [clusters, setClusters] = useState<ClusterInfo[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const discoverClusters = useCallback(async () => {
    if (!isAuthenticated) {
      setError('Not authenticated');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const discoveredClusters = await clusterApi.getClusters();
      setClusters(discoveredClusters);

      if (discoveredClusters.length === 0) {
        setError('No clusters found. Check your IAM permissions.');
      }
    } catch (err: unknown) {
      setError(formatApiError(toApiError(err)));
      setClusters([]);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  const selectCluster = useCallback(
    async (clusterName: string) => {
      if (!isAuthenticated) {
        setError('Not authenticated');
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await clusterApi.selectCluster(clusterName);

        if (response.success) {
          setSelectedCluster(clusterName);
        } else {
          throw new Error('Failed to select cluster');
        }
      } catch (err: unknown) {
        const apiErr = toApiError(err);
        const msg = formatApiError(apiErr);
        setError(msg);
        throw new Error(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [isAuthenticated]
  );

  const clearSelection = useCallback(() => {
    setSelectedCluster(null);
  }, []);

  useEffect(() => {
    const autoDiscoverAndSelect = async () => {
      if (!isAuthenticated) return;

      try {
        const discoveredClusters = await clusterApi.getClusters();
        if (discoveredClusters.length > 0) {
          setClusters(discoveredClusters);
          const currentCluster = discoveredClusters[0].name;
          const response = await clusterApi.selectCluster(currentCluster);
          if (response.success) {
            setSelectedCluster(currentCluster);
          }
        }
      } catch (err: unknown) {
        setError(formatApiError(toApiError(err)));
      }
    };

    if (isAuthenticated && clusters.length === 0 && !selectedCluster) {
      autoDiscoverAndSelect();
    }
  }, [isAuthenticated, clusters.length, selectedCluster]);

  useEffect(() => {
    if (!isAuthenticated) {
      setSelectedCluster(null);
      setClusters([]);
    }
  }, [isAuthenticated]);

  return {
    clusters,
    selectedCluster,
    isLoading,
    error,
    discoverClusters,
    selectCluster,
    clearSelection,
  };
};
