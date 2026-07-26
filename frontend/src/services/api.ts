import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { KionCredentials, KubeconfigCredentials, KubeconfigUpload, KubeconfigParseResponse, KubeconfigAuthRequest } from '../types/credentials';
import { ApiClientError, toApiError } from '../utils/apiError';

/**
 * Get the current API base URL (checked at request time, not module load time)
 * This allows runtime configuration to be loaded after module imports.
 * 
 * Base API URL determination (in order of precedence):
 * 1. Runtime config from /api/config (window.__CONFIG__.apiBaseUrl)
 * 2. Build-time env var REACT_APP_API_URL
 * 3. Default /api
 */
function getApiBaseUrl(): string {
  // Check runtime config first (loaded by initializeApp in index.tsx)
  const runtimeConfig = (window as any).__CONFIG__;
  if (runtimeConfig && runtimeConfig.apiBaseUrl) {
    return runtimeConfig.apiBaseUrl;
  }
  
  // Fall back to build-time environment variable
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // Final default
  return '/api';
}

/**
 * Axios instance with default configuration
 * Uses a request interceptor to dynamically determine baseURL at request time
 */
const apiClient: AxiosInstance = axios.create({
  // Agent turns can exceed 30s; fail the turn without stranding the UI.
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Include cookies for session management
});

/**
 * Request interceptor — set baseURL dynamically and attach session ID
 */
apiClient.interceptors.request.use((config) => {
  // Dynamically set baseURL at request time (supports runtime config changes)
  const baseUrl = getApiBaseUrl();
  config.baseURL = baseUrl;

  // Attach session ID from localStorage as x-session-id header
  const sessionId = localStorage.getItem('sessionId');
  if (sessionId) {
    config.headers['x-session-id'] = sessionId;
  }

  // Correlation id for logs ↔ UI
  if (!config.headers['X-Request-Id'] && !config.headers['x-request-id']) {
    config.headers['X-Request-Id'] = Math.random().toString(16).slice(2, 14);
  }
  return config;
});

/**
 * Response interceptor — normalize failures to ApiClientError
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError = toApiError(error);
    console.error(
      `[api] code=${apiError.code} status=${apiError.status ?? '-'} request_id=${apiError.requestId ?? '-'} message=${apiError.message}`
    );
    return Promise.reject(new ApiClientError(apiError));
  }
);

/**
 * Authentication API
 */
export const authApi = {
  /**
   * Submit AWS Kion credentials for authentication
   * @param credentials - AWS Kion credentials
   * @returns Promise with authentication response
   */
  async login(credentials: KionCredentials): Promise<{ success: boolean; sessionId: string }> {
    const response = await apiClient.post('/credentials/aws', {
      access_key_id: credentials.accessKeyId,
      secret_access_key: credentials.secretAccessKey,
      session_token: credentials.sessionToken,
      region: credentials.region,
    });
    return response.data;
  },

  /**
   * Submit kubeconfig for local cluster authentication
   * @param credentials - Kubeconfig credentials
   * @returns Promise with authentication response
   */
  async loginKubeconfig(credentials: KubeconfigCredentials): Promise<{ success: boolean; sessionId: string }> {
    console.log('[authApi] loginKubeconfig called with:', credentials);
    try {
      const response = await apiClient.post('/credentials/kubeconfig', {
        kubeconfig_path: credentials.kubeconfigPath,
      });
      console.log('[authApi] loginKubeconfig response status:', response.status);
      console.log('[authApi] loginKubeconfig response data:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('[authApi] loginKubeconfig error:', error);
      console.error('[authApi] Error config:', error.config);
      console.error('[authApi] Error response:', error.response);
      throw error;
    }
  },

  /**
   * Parse kubeconfig content to get available contexts
   * @param upload - Kubeconfig upload with raw YAML content
   * @returns Promise with parsed contexts
   */
  async parseKubeconfig(upload: KubeconfigUpload): Promise<KubeconfigParseResponse> {
    console.log('[authApi] parseKubeconfig called');
    try {
      const response = await apiClient.post('/credentials/kubeconfig/parse', {
        content: upload.content,
      });
      console.log('[authApi] parseKubeconfig response:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('[authApi] parseKubeconfig error:', error);
      console.error('[authApi] Error response:', error.response);
      throw error;
    }
  },

  /**
   * Authenticate with kubeconfig content and selected context
   * @param request - Kubeconfig auth request with content and selected context
   * @returns Promise with authentication response
   */
  async authKubeconfig(request: KubeconfigAuthRequest): Promise<{ success: boolean; sessionId: string }> {
    console.log('[authApi] authKubeconfig called with context:', request.context);
    try {
      const response = await apiClient.post('/credentials/kubeconfig/auth', {
        content: request.content,
        context: request.context,
      });
      console.log('[authApi] authKubeconfig response:', response.data);
      // Backend returns snake_case session_id; normalize to camelCase
      const data = response.data;
      return {
        success: data.success,
        sessionId: data.session_id ?? data.sessionId,
      };
    } catch (error: any) {
      console.error('[authApi] authKubeconfig error:', error);
      console.error('[authApi] Error response:', error.response);
      throw error;
    }
  },

  /**
   * Get current credential status
   * @returns Promise with credential status
   */
  async getStatus(): Promise<{
    status: 'active' | 'expiring_soon' | 'expired' | 'no_credentials';
    ttl_seconds?: number;
    expires_at?: string;
  }> {
    const response = await apiClient.get('/credentials/aws/status');
    return response.data;
  },

  /**
   * Delete current credentials (logout)
   * @returns Promise with deletion confirmation
   */
  async logout(): Promise<{ success: boolean }> {
    const response = await apiClient.delete('/credentials/aws');
    return response.data;
  },
};

/**
 * Cluster API
 */
export const clusterApi = {
  /**
   * Discover available EKS clusters
   * @returns Promise with list of clusters
   */
  async getClusters(): Promise<any[]> {
    const response = await apiClient.get('/clusters');
    return response.data.clusters ?? response.data;
  },

  /**
   * Select a target cluster
   * @param clusterName - Name of the cluster to select
   * @returns Promise with selection confirmation
   */
  async selectCluster(clusterName: string): Promise<{ success: boolean }> {
    const response = await apiClient.post('/clusters/select', {
      cluster_name: clusterName,
    });
    return response.data;
  },
};

/**
 * K8sGPT Results API
 */
export const resultsApi = {
  /**
   * Get all K8sGPT Result CRDs for the selected cluster
   * @param filters - Optional filters for severity, namespace, kind
   * @returns Promise with list of results
   */
  async getResults(filters?: {
    severity?: string[];
    namespace?: string[];
    kind?: string[];
  }): Promise<any[]> {
    const params = new URLSearchParams();
    
    if (filters?.severity) {
      filters.severity.forEach(s => params.append('severity', s));
    }
    if (filters?.namespace) {
      filters.namespace.forEach(n => params.append('namespace', n));
    }
    if (filters?.kind) {
      filters.kind.forEach(k => params.append('kind', k));
    }
    
    const queryString = params.toString();
    const url = queryString ? `/results?${queryString}` : '/results';
    
    const response = await apiClient.get(url);
    // Backend returns { results: [...], count: N } — extract the array
    return response.data.results ?? response.data;
  },

  /**
   * Get a specific K8sGPT Result by ID
   * @param id - Result ID
   * @returns Promise with result details
   */
  async getResultById(id: string): Promise<any> {
    const response = await apiClient.get(`/results/${id}`);
    return response.data;
  },
};

export default apiClient;
