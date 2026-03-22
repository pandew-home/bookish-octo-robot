import { useState, useCallback, useEffect } from 'react';
import { ClusterInfo } from '../types/cluster';
import { clusterApi } from '../services/api';

export interface UseClusterState {
  clusters: ClusterInfo[];
  selectedCluster: string | null;
  isLoading: boolean;
  error: string | null;
  discoverClusters: () => Promise<void>;
  selectCluster: (clusterName: string) => Promise<void>;
  clearSelection: () => void;
}

/**
 * React hook to manage cluster discovery, selection, and switching
 * 
 * Features:
 * - Discover available EKS clusters using user's credentials
 * - Select a target cluster for operations
 * - Handle cluster switching (generates new bearer token, updates K8s clients)
 * - Maintain cluster-specific state
 * 
 * Requirements: 2.1, 2.2, 2.3, 13.1, 13.2
 */
export const useCluster = (isAuthenticated: boolean): UseClusterState => {
  const [clusters, setClusters] = useState<ClusterInfo[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Discover available EKS clusters using user's Kion credentials
   * Caches results for 300 seconds on backend
   */
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
      
      // If no clusters found, set appropriate error
      if (discoveredClusters.length === 0) {
        setError('No clusters found. Check your IAM permissions.');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to discover clusters';
      setError(errorMessage);
      setClusters([]);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  /**
   * Select a target cluster
   * Generates EKS bearer token and configures K8s API clients on backend
   * Switches conversation history to selected cluster
   */
  const selectCluster = useCallback(async (clusterName: string) => {
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
        
        // Note: Backend handles:
        // - Bearer token generation (Requirement 13.1)
        // - K8s client reconfiguration (Requirement 13.2)
        // - Conversation history switching (Requirement 13.3)
        // - Cache invalidation (Requirement 13.4)
      } else {
        throw new Error('Failed to select cluster');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to select cluster';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  /**
   * Clear cluster selection
   */
  const clearSelection = useCallback(() => {
    setSelectedCluster(null);
  }, []);

  /**
   * Auto-discover clusters when authenticated and auto-select the current cluster
   */
  useEffect(() => {
    const autoDiscoverAndSelect = async () => {
      if (!isAuthenticated) return;

      try {
        const discoveredClusters = await clusterApi.getClusters();
        if (discoveredClusters.length > 0) {
          setClusters(discoveredClusters);
          // Auto-select the first (current) cluster
          const currentCluster = discoveredClusters[0].name;
          setSelectedCluster(currentCluster);
          await clusterApi.selectCluster(currentCluster);
        }
      } catch (err: any) {
        const errorMessage = err.response?.data?.detail || err.message || 'Failed to discover clusters';
        setError(errorMessage);
      }
    };

    if (isAuthenticated && clusters.length === 0 && !selectedCluster) {
      autoDiscoverAndSelect();
    }
  }, [isAuthenticated, clusters.length, selectedCluster]);

  /**
   * Clear selection when authentication is lost
   */
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
