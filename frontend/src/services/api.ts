import axios, { AxiosInstance } from 'axios';
import { KionCredentials, KubeconfigCredentials, KubeconfigUpload, KubeconfigParseResponse, KubeconfigAuthRequest } from '../types/credentials';

/**
 * Base API URL - defaults to /api for production, can be overridden for development
 */
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

/**
 * Axios instance with default configuration
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Include cookies for session management
});

/**
 * Response interceptor for handling common errors
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Credentials expired or invalid
      console.error('Authentication failed:', error.response.data);
    } else if (error.response?.status === 429) {
      // Rate limit exceeded
      console.error('Rate limit exceeded:', error.response.data);
    }
    return Promise.reject(error);
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
      return response.data;
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
    return response.data;
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
    return response.data;
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

/**
 * Solutions/Knowledge Base API
 */
export const solutionsApi = {
  /**
   * Submit a new solution to the knowledge base
   * @param solution - Solution data
   * @returns Promise with submission confirmation
   */
  async submitSolution(solution: {
    title: string;
    description: string;
    tags: string[];
    runbookUrl?: string;
    automationScript?: string;
    estimatedFixTime?: number;
    sourceConversation?: string;
  }): Promise<{ success: boolean; id: string }> {
    const response = await apiClient.post('/solutions', {
      title: solution.title,
      description: solution.description,
      tags: solution.tags,
      runbook_url: solution.runbookUrl,
      automation_script: solution.automationScript,
      estimated_fix_time: solution.estimatedFixTime,
      source_conversation: solution.sourceConversation,
    });
    return response.data;
  },

  /**
   * Get all solutions from the knowledge base
   * @param filters - Optional filters for tags, pagination
   * @returns Promise with list of solutions
   */
  async getSolutions(filters?: {
    tags?: string[];
    limit?: number;
    offset?: number;
  }): Promise<any[]> {
    const params = new URLSearchParams();
    
    if (filters?.tags) {
      filters.tags.forEach(t => params.append('tags', t));
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    if (filters?.offset) {
      params.append('offset', filters.offset.toString());
    }
    
    const queryString = params.toString();
    const url = queryString ? `/solutions?${queryString}` : '/solutions';
    
    const response = await apiClient.get(url);
    return response.data;
  },

  /**
   * Search knowledge base using semantic search
   * @param query - Search query
   * @param topK - Number of results to return
   * @returns Promise with search results
   */
  async searchKnowledgeBase(query: string, topK: number = 5): Promise<any[]> {
    const response = await apiClient.get('/kb/search', {
      params: { query, top_k: topK },
    });
    return response.data;
  },
};

export default apiClient;
