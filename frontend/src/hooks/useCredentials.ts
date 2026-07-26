import { useState, useCallback } from 'react';
import { KionCredentials, KubeconfigCredentials } from '../types/credentials';
import { authApi } from '../services/api';
import { useCredentialStatus } from './useCredentialStatus';
import { formatApiError, toApiError } from '../utils/apiError';

export interface UseCredentialsState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  accountId?: string;
  userArn?: string;
  expiresAt?: string;
  timeRemaining: number | null;
  login: (credentials: KionCredentials) => Promise<void>;
  loginKubeconfig: (credentials: KubeconfigCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

/**
 * React hook to manage Kion AWS credential submission, status polling, and expiration
 * 
 * Features:
 * - Submit credentials for authentication
 * - Poll credential status every 30 seconds
 * - Calculate time remaining until expiry
 * - Handle re-authentication flow when credentials expire
 * - Logout to remove credentials
 * 
 * Requirements: 1.1, 1.2, 1.3, 1.4
 */
export const useCredentials = (): UseCredentialsState => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Use the existing credential status hook for polling
  const { status, timeRemaining, refresh } = useCredentialStatus();

  /**
   * Submit Kion credentials for authentication
   * Validates credentials via STS GetCallerIdentity and stores them with TTL
   */
  const login = useCallback(async (credentials: KionCredentials) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await authApi.login(credentials);
      
      if (!response.success) {
        throw new Error('Authentication failed');
      }

      if (response.sessionId) {
        localStorage.setItem('sessionId', response.sessionId);
      }

      // Refresh status after successful login
      await refresh();
    } catch (err: unknown) {
      const msg = formatApiError(toApiError(err));
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [refresh]);

  /**
   * Submit kubeconfig for local cluster authentication
   */
  const loginKubeconfig = useCallback(async (credentials: KubeconfigCredentials) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await authApi.loginKubeconfig(credentials);

      if (!response.success) {
        throw new Error('Kubeconfig authentication failed');
      }

      await refresh();
    } catch (err: unknown) {
      const msg = formatApiError(toApiError(err));
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [refresh]);

  /**
   * Remove credentials from backend (logout)
   */
  const logout = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      await authApi.logout();
      localStorage.removeItem('sessionId');

      await refresh();
    } catch (err: unknown) {
      const msg = formatApiError(toApiError(err));
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [refresh]);

  // Determine authentication state
  const isAuthenticated = status?.present === true && status?.expired !== true;

  return {
    isAuthenticated,
    isLoading,
    error,
    accountId: status?.account_id,
    userArn: status?.user_arn,
    expiresAt: status?.expires_at,
    timeRemaining,
    login,
    loginKubeconfig,
    logout,
    refresh,
  };
};
