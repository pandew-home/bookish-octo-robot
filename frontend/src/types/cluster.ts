/**
 * EKS Cluster information interface
 * Represents a discovered EKS cluster
 */
export interface ClusterInfo {
  name: string;
  endpoint: string;
  version: string;
  status: string;
  region: string;
}

/**
 * Environment type derived from cluster name
 * Used for theming the cluster selector
 */
export type ClusterEnvironment = 'dev' | 'staging' | 'prod' | 'unknown';

/**
 * Determines the environment type from cluster name
 * @param clusterName - The name of the cluster
 * @returns The environment type
 */
export function getClusterEnvironment(clusterName: string): ClusterEnvironment {
  const lowerName = clusterName.toLowerCase();
  
  if (lowerName.includes('dev') || lowerName.includes('development')) {
    return 'dev';
  }
  if (lowerName.includes('stag') || lowerName.includes('staging')) {
    return 'staging';
  }
  if (lowerName.includes('prod') || lowerName.includes('production')) {
    return 'prod';
  }
  
  return 'unknown';
}

/**
 * Environment color mapping for theming
 */
export const ENVIRONMENT_COLORS = {
  dev: {
    primary: '#4caf50',    // Green
    light: '#81c784',
    dark: '#388e3c',
  },
  staging: {
    primary: '#ff9800',    // Orange
    light: '#ffb74d',
    dark: '#f57c00',
  },
  prod: {
    primary: '#f44336',    // Red
    light: '#e57373',
    dark: '#d32f2f',
  },
  unknown: {
    primary: '#9e9e9e',    // Grey
    light: '#bdbdbd',
    dark: '#616161',
  },
} as const;
