/**
 * Chat message citation interface
 */
export interface Citation {
  documentId: string;
  title: string;
  snippet: string;
  relevanceScore: number;
  usageCount?: number;
  successRate?: number;
}

/**
 * K8sGPT finding interface
 */
export interface K8sGPTFinding {
  name: string;
  kind: string;
  namespace: string;
  severity: string;
  problem: string;
}

/**
 * Chat error types for styling
 */
export type ChatErrorType = 'auth_error' | 'cluster_unreachable' | 'rate_limited' | 'timeout' | 'connection_error' | 'rbac_forbidden';

/**
 * Chat message interface
 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  k8sgptFindings?: K8sGPTFinding[];
  safetyNotice?: string;
  timestamp: string;
  queryType?: string;
  loading?: boolean;
  cluster?: string;
  errorType?: ChatErrorType;
  /** Soft agent warnings/errors from a successful (or partial) HTTP 200 turn */
  backendErrors?: { type: string; message: string; severity: string; code?: string }[];
}

/**
 * Chat history export format
 */
export interface ConversationExport {
  problem: string;
  investigation: string;
  rootCause: string;
  solution: string;
  verification: string;
  timestamp: string;
  cluster: string;
}
