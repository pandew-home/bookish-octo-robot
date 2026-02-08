/**
 * K8sGPT Result CRD interface
 * Represents a diagnostic result from K8sGPT Operator
 */
export interface K8sGPTResult {
  name: string;
  kind: string;
  namespace: string;
  severity: 'low' | 'medium' | 'high';
  problem: string;
  solution: string;
  analyzer: string;
  timestamp: string;
  details?: Record<string, any>;
}

/**
 * Severity level type
 */
export type SeverityLevel = 'low' | 'medium' | 'high';

/**
 * Filter options for K8sGPT results
 */
export interface ResultsFilter {
  severity?: SeverityLevel[];
  namespace?: string[];
  kind?: string[];
}

/**
 * Get severity color for display
 * @param severity - The severity level
 * @returns MUI color name
 */
export function getSeverityColor(severity: SeverityLevel): 'error' | 'warning' | 'info' {
  switch (severity) {
    case 'high':
      return 'error';
    case 'medium':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'info';
  }
}

/**
 * Get severity icon
 * @param severity - The severity level
 * @returns Emoji icon
 */
export function getSeverityIcon(severity: SeverityLevel): string {
  switch (severity) {
    case 'high':
      return '🔴';
    case 'medium':
      return '🟡';
    case 'low':
      return '🟢';
    default:
      return '⚪';
  }
}

/**
 * Get severity display name
 * @param severity - The severity level
 * @returns Display name
 */
export function getSeverityDisplayName(severity: SeverityLevel): string {
  switch (severity) {
    case 'high':
      return 'High';
    case 'medium':
      return 'Medium';
    case 'low':
      return 'Low';
    default:
      return 'Unknown';
  }
}
