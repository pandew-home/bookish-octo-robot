/**
 * Weather state type representing cluster health
 */
export type WeatherState = 'sunny' | 'partly-cloudy' | 'cloudy' | 'rainy' | 'stormy';

/**
 * Cluster tool information
 */
export interface ClusterToolInfo {
  name: string;
  version: string;
  category: string;
  deploymentAgeDays?: number;
  status: 'healthy' | 'degraded' | 'unknown';
}

/**
 * K8sGPT Result summary for weather display
 */
export interface K8sGPTResultSummary {
  name: string;
  kind: string;
  namespace: string;
  severity: 'low' | 'medium' | 'high';
  problem: string;
  solution?: string;
  analyzer?: string;
  timestamp?: string;
}

/**
 * Weather data interface
 * Represents cluster health status derived from K8sGPT Results
 */
export interface WeatherData {
  state: WeatherState;
  clusterName: string;
  clusterVersion: string;
  k8sgptResultCount: number;
  topIssues?: K8sGPTResultSummary[];
  clusterTools: ClusterToolInfo[];
  timestamp: string;
}

/**
 * Weather icons mapping
 */
export const WEATHER_ICONS: Record<WeatherState, string> = {
  sunny: '☀️',
  'partly-cloudy': '🌤️',
  cloudy: '☁️',
  rainy: '🌧️',
  stormy: '⛈️',
};

/**
 * Weather display names
 */
export const WEATHER_NAMES: Record<WeatherState, string> = {
  sunny: 'Sunny',
  'partly-cloudy': 'Partly Cloudy',
  cloudy: 'Cloudy',
  rainy: 'Rainy',
  stormy: 'Stormy',
};

/**
 * Weather descriptions
 */
export const WEATHER_DESCRIPTIONS: Record<WeatherState, string> = {
  sunny: 'All systems operational',
  'partly-cloudy': 'Minor issues detected',
  cloudy: 'Several issues need attention',
  rainy: 'Multiple issues affecting cluster',
  stormy: 'Critical issues require immediate action',
};

/**
 * Get weather color for display
 */
export function getWeatherColor(state: WeatherState): string {
  switch (state) {
    case 'sunny':
      return '#4caf50'; // Green
    case 'partly-cloudy':
      return '#8bc34a'; // Light green
    case 'cloudy':
      return '#ff9800'; // Orange
    case 'rainy':
      return '#ff5722'; // Deep orange
    case 'stormy':
      return '#f44336'; // Red
    default:
      return '#9e9e9e'; // Grey
  }
}
